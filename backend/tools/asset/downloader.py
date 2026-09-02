"""
Secure streaming asset downloader with zip-slip protection,
max size safeguards, and archive extraction into Unity project folders.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import zipfile
from pathlib import Path

import httpx

from backend.config import get_settings
from backend.tools.asset.exceptions import DownloadError, ZipSlipSecurityError

logger = logging.getLogger("backend.tools.asset.downloader")


def sanitize_filename(name: str) -> str:
    """Sanitizes filename removing illegal characters and path separators."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name)
    clean = clean.strip(". ")
    return clean or "asset_file"


def extract_filename_from_url(url: str, default: str = "downloaded_asset") -> str:
    """Extracts a clean filename from a URL or query string."""
    parsed = urllib.parse.urlparse(url)
    # Check for ambientcg ?file= parameter
    query_params = urllib.parse.parse_qs(parsed.query)
    if "file" in query_params:
        return sanitize_filename(query_params["file"][0])

    path_name = Path(parsed.path).name
    if path_name and "." in path_name:
        return sanitize_filename(path_name)

    return sanitize_filename(default)


async def download_file_stream(
    url: str,
    target_path: Path,
    max_bytes: int | None = None,
    timeout_seconds: float | None = None,
) -> int:
    """
    Streams a remote URL directly to disk with size limits and timeout enforcement.
    Returns the total bytes written.
    """
    settings = get_settings()
    max_size = max_bytes or settings.max_asset_download_size_bytes
    timeout = timeout_seconds or settings.asset_download_timeout_seconds

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".tmp")

    headers = {"User-Agent": "Visora-MCP/0.1.1 (Unity Agent; https://github.com/AmaLS367/Visora)"}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code >= 400:
                    raise DownloadError(f"HTTP error {response.status_code} while fetching {url}")

                content_len = response.headers.get("content-length")
                if content_len and int(content_len) > max_size:
                    raise DownloadError(
                        f"File size ({content_len} bytes) exceeds maximum permitted limit ({max_size} bytes)."
                    )

                bytes_written = 0
                with temp_path.open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        bytes_written += len(chunk)
                        if bytes_written > max_size:
                            raise DownloadError(
                                f"Download exceeded maximum permitted size of {max_size} bytes while streaming."
                            )
                        f.write(chunk)

        # Atomically rename temp file to target
        if temp_path.exists():
            temp_path.replace(target_path)

        return bytes_written

    except Exception as exc:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        if isinstance(exc, DownloadError):
            raise
        raise DownloadError(f"Download from {url} failed: {exc}") from exc


def safe_extract_zip(
    zip_path: Path,
    target_dir: Path,
    skip_system_files: bool = True,
) -> list[str]:
    """
    Safely extracts a ZIP archive into target_dir with strict Zip-Slip path traversal protection.
    Returns relative paths of all extracted files.
    """
    target_dir_resolved = target_dir.resolve()
    target_dir_resolved.mkdir(parents=True, exist_ok=True)
    extracted_rel_paths: list[str] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            # Skip directory entries
            if member.is_dir():
                continue

            member_name = member.filename

            # Zip-slip validation: check destination stays strictly inside target_dir
            dest_path = (target_dir_resolved / member_name).resolve()
            try:
                dest_path.relative_to(target_dir_resolved)
            except ValueError as err:
                raise ZipSlipSecurityError(
                    f"Security Alert: Archive member '{member_name}' attempts path traversal outside target directory."
                ) from err

            # Skip OS junk like __MACOSX or .DS_Store
            if skip_system_files:
                parts = Path(member_name).parts
                if any((p.startswith(".") and p not in {".", ".."}) or p == "__MACOSX" for p in parts):
                    continue

            # Disallow dangerous executables
            if dest_path.suffix.lower() in {".exe", ".bat", ".cmd", ".sh", ".dll", ".so"}:
                logger.warning(f"Skipping dangerous executable in archive: {member_name}")
                continue

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as source, dest_path.open("wb") as target:
                target.write(source.read())

            extracted_rel_paths.append(str(dest_path.relative_to(target_dir_resolved)).replace("\\", "/"))

    return extracted_rel_paths
