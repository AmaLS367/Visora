"""Secure staging, remote-download, and archive-validation helpers for assets."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import shutil
import socket
import stat
import tarfile
import urllib.parse
import zipfile
from collections.abc import Iterable
from pathlib import Path

import httpx

from backend.config import get_settings
from backend.tools.asset.exceptions import ArchiveLimitError, AssetSecurityError, DownloadError, ZipSlipSecurityError

logger = logging.getLogger("backend.tools.asset.downloader")

ALLOWED_ASSET_EXTENSIONS = frozenset(
    {
        ".fbx",
        ".obj",
        ".gltf",
        ".glb",
        ".png",
        ".jpg",
        ".jpeg",
        ".tga",
        ".exr",
        ".hdr",
        # Not standalone "assets" themselves, but load-bearing companions our supported model
        # formats require to actually work: a non-binary .gltf's mesh/skin/bone data lives in an
        # externally referenced .bin buffer, and a .obj's material assignments live in its .mtl.
        # Verified live: a real Sketchfab download (non-binary glTF export) has its entire
        # geometry in scene.bin - dropping it during zip extraction (as an "unsupported"
        # extension) silently produced a mesh-less, broken asset instead of an import failure.
        ".bin",
        ".mtl",
    }
)
ALLOWED_DOWNLOAD_EXTENSIONS = ALLOWED_ASSET_EXTENSIONS | {".zip"}
UNITYPACKAGE_EXTENSION = ".unitypackage"
_REDIRECT_CODES = {301, 302, 303, 307, 308}
_CHUNK_SIZE = 65_536


def sanitize_filename(name: str) -> str:
    """Sanitize a filename, never allowing it to contain a path separator."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip(". ")
    return clean or "asset_file"


def extract_filename_from_url(url: str, default: str = "downloaded_asset") -> str:
    """Extract a safe filename from an URL path or its ambientCG file query."""
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)
    if "file" in query_params:
        return sanitize_filename(query_params["file"][0])
    path_name = Path(parsed.path).name
    return sanitize_filename(path_name) if path_name and "." in path_name else sanitize_filename(default)


def validate_asset_extension(path: Path, *, allow_zip: bool = False, allow_unitypackage: bool = False) -> None:
    """Reject every file type except the explicitly supported import formats."""
    suffix = path.suffix.lower()
    allowed = ALLOWED_ASSET_EXTENSIONS | ({".zip"} if allow_zip else set())
    if allow_unitypackage:
        allowed = allowed | {UNITYPACKAGE_EXTENSION}
    if suffix not in allowed:
        raise AssetSecurityError(f"Unsupported or unsafe asset extension: {suffix or '<none>'}")


def _is_public_ip(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


async def validate_remote_url(url: str) -> None:
    """Allow only HTTPS URLs resolving exclusively to globally routable addresses."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise AssetSecurityError("Asset downloads require an absolute HTTPS URL with a hostname.")
    if parsed.username or parsed.password:
        raise AssetSecurityError("Asset download URLs must not contain user credentials.")

    port = parsed.port or 443
    try:
        addresses = await asyncio.get_running_loop().run_in_executor(
            None, lambda: socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        )
    except OSError as exc:
        raise AssetSecurityError(f"Could not resolve asset download host {parsed.hostname!r}: {exc}") from exc

    resolved = {str(entry[4][0]) for entry in addresses}
    if not resolved or any(not _is_public_ip(address) for address in resolved):
        raise AssetSecurityError("Asset download host resolves to a non-public network address.")


async def download_file_stream(
    url: str,
    target_path: Path,
    max_bytes: int | None = None,
    timeout_seconds: float | None = None,
) -> int:
    """Download into quarantine with size limits and SSRF-safe manual redirects."""
    settings = get_settings()
    max_size = max_bytes or settings.max_asset_download_size_bytes
    timeout = timeout_seconds or settings.asset_download_timeout_seconds
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    headers = {"User-Agent": "Visora-MCP/0.1.2 (Unity Agent; https://github.com/AmaLS367/Visora)"}
    current_url = url

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for redirect_count in range(6):
                await validate_remote_url(current_url)
                async with client.stream("GET", current_url, headers=headers) as response:
                    if response.status_code in _REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise DownloadError("Redirect response did not include a Location header.")
                        if redirect_count == 5:
                            raise DownloadError("Asset download exceeded the maximum of 5 redirects.")
                        current_url = urllib.parse.urljoin(current_url, location)
                        continue
                    if response.status_code >= 400:
                        raise DownloadError(f"HTTP error {response.status_code} while fetching {current_url}")

                    content_len = response.headers.get("content-length")
                    if content_len and int(content_len) > max_size:
                        raise DownloadError(
                            f"File size ({content_len} bytes) exceeds maximum permitted limit ({max_size} bytes)."
                        )

                    bytes_written = 0
                    with temp_path.open("xb") as output:
                        async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
                            bytes_written += len(chunk)
                            if bytes_written > max_size:
                                raise DownloadError(
                                    f"Download exceeded maximum permitted size of {max_size} bytes while streaming."
                                )
                            output.write(chunk)
                    temp_path.replace(target_path)
                    return bytes_written
        raise DownloadError("Asset download did not receive a final response.")
    except Exception as exc:
        temp_path.unlink(missing_ok=True)
        if isinstance(exc, (DownloadError, AssetSecurityError)):
            raise
        raise DownloadError(f"Download from {url} failed: {exc}") from exc


def _is_system_file(member_name: str) -> bool:
    parts = Path(member_name).parts
    return any((part.startswith(".") and part not in {".", ".."}) or part == "__MACOSX" for part in parts)


def _validate_zip_members(zf: zipfile.ZipFile, target_dir: Path) -> list[zipfile.ZipInfo]:
    settings = get_settings()
    target_root = target_dir.resolve()
    members: list[zipfile.ZipInfo] = []
    total_size = 0

    archive_members = zf.infolist()
    if len(archive_members) > settings.max_asset_archive_entries:
        raise ArchiveLimitError(f"Archive exceeds {settings.max_asset_archive_entries} entries.")
    for member in archive_members:
        if member.is_dir() or _is_system_file(member.filename):
            continue
        if stat.S_ISLNK(member.external_attr >> 16):
            raise AssetSecurityError(f"Archive member is a symbolic link: {member.filename}")

        destination = (target_root / member.filename).resolve()
        try:
            destination.relative_to(target_root)
        except ValueError as exc:
            raise ZipSlipSecurityError(
                f"Security Alert: Archive member '{member.filename}' attempts path traversal outside target directory."
            ) from exc

        try:
            validate_asset_extension(destination)
        except AssetSecurityError:
            # Real-world provider archives bundle companion files we don't import alongside
            # the actual asset (e.g. every ambientCG texture zip ships a .usdc, .blend, .mtlx,
            # and .tres next to the .png files). Aborting the whole archive over one irrelevant
            # sidecar file made every ambientCG download fail outright. Skip unsupported members
            # instead of rejecting the archive; the "no supported files at all" check below still
            # catches archives that are genuinely useless to us.
            continue
        if member.file_size > settings.max_asset_archive_entry_size_bytes:
            raise ArchiveLimitError(f"Archive entry exceeds per-file limit: {member.filename}")
        total_size += member.file_size
        if total_size > settings.max_asset_archive_uncompressed_size_bytes:
            raise ArchiveLimitError("Archive exceeds total uncompressed size limit.")
        if member.file_size and (
            member.compress_size == 0
            or member.file_size / member.compress_size > settings.max_asset_archive_compression_ratio
        ):
            raise ArchiveLimitError(f"Archive entry exceeds compression ratio limit: {member.filename}")
        members.append(member)

    if not members:
        raise AssetSecurityError("Archive does not contain any supported asset files.")
    return members


def safe_extract_zip(zip_path: Path, target_dir: Path) -> list[str]:
    """Validate an entire ZIP before streaming it to a temporary extraction directory."""
    extracted: list[str] = []
    created_target = False
    try:
        if target_dir.exists():
            raise AssetSecurityError(f"Archive extraction target already exists: {target_dir}")
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = _validate_zip_members(archive, target_dir)
            target_root = target_dir.resolve()
            target_root.mkdir(parents=True, exist_ok=False)
            created_target = True
            for member in members:
                destination = (target_root / member.filename).resolve()
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, destination.open("xb") as output:
                    while chunk := source.read(_CHUNK_SIZE):
                        output.write(chunk)
                extracted.append(str(destination.relative_to(target_root)).replace("\\", "/"))
        return extracted
    except Exception:
        if created_target:
            shutil.rmtree(target_dir, ignore_errors=True)
        raise


def validate_unitypackage_contents(package_path: Path, assets_path: Path) -> list[str]:
    """Preflight Unity package asset paths before its opt-in native import."""
    assets_root = assets_path.resolve()
    asset_paths: list[str] = []
    try:
        with tarfile.open(package_path, "r:*") as package:
            for member in package.getmembers():
                if not member.isfile() or not member.name.endswith("/pathname"):
                    continue
                source = package.extractfile(member)
                if source is None:
                    raise AssetSecurityError("Unity package pathname entry could not be read.")
                raw_path = source.read().decode("utf-8").strip().replace("\\", "/")
                candidate = (assets_root.parent / raw_path).resolve()
                try:
                    candidate.relative_to(assets_root)
                except ValueError as exc:
                    raise AssetSecurityError(f"Unity package contains unsafe path: {raw_path}") from exc
                validate_asset_extension(candidate)
                if candidate.exists():
                    raise AssetSecurityError(f"Unity package would overwrite existing asset: {raw_path}")
                asset_paths.append(raw_path)
    except (tarfile.TarError, UnicodeDecodeError) as exc:
        raise AssetSecurityError(f"Invalid Unity package: {exc}") from exc
    if not asset_paths:
        raise AssetSecurityError("Unity package does not contain supported importable assets.")
    return asset_paths


def iter_supported_extensions() -> Iterable[str]:
    """Return allowed extensions for concise user-facing documentation."""
    return sorted(ALLOWED_DOWNLOAD_EXTENSIONS)
