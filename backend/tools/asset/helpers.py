"""
Helper utilities for Unity asset staging, path resolution, safety validation,
and bridge execution operations.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

from backend.config import get_settings
from backend.schemas.asset import Vector3
from backend.tools.asset import common
from backend.tools.asset.exceptions import AssetError, AssetSecurityError
from backend.tools.asset.scripts import (
    _get_project_paths_code,
    _import_asset_code,
    _instantiate_asset_code,
)

logger = common.logger

ModelVector3 = Vector3
MODEL_EXTENSIONS = {".glb", ".gltf", ".fbx", ".obj"}


def resolve_target_folder(assets_path: Path, requested_folder: str | None) -> tuple[Path, str]:
    """Resolve a target folder and prove it stays inside the Unity Assets directory."""
    assets_root = assets_path.resolve()
    raw_folder = (requested_folder or get_settings().default_asset_import_dir).replace("\\", "/").strip()
    if not raw_folder:
        raw_folder = "Assets"
    folder_path = Path(raw_folder)
    if folder_path.is_absolute():
        raise AssetSecurityError("target_folder must be relative to the Unity project or Assets directory.")
    destination = (
        (assets_root.parent / folder_path).resolve()
        if folder_path.parts and folder_path.parts[0] == "Assets"
        else (assets_root / folder_path).resolve()
    )
    try:
        relative = destination.relative_to(assets_root)
    except ValueError as exc:
        raise AssetSecurityError("target_folder must resolve inside the Unity Assets directory.") from exc
    unity_path = "Assets" + (f"/{relative.as_posix()}" if relative.parts else "")
    return destination, unity_path


def resolve_cache_root(project_path: Path, assets_path: Path) -> Path:
    """Resolve the configured quarantine root and reject an Assets-contained cache."""
    configured = Path(get_settings().asset_cache_dir)
    cache_root = (configured if configured.is_absolute() else project_path / configured).resolve()
    try:
        cache_root.relative_to(assets_path.resolve())
    except ValueError:
        cache_root.mkdir(parents=True, exist_ok=True)
        return cache_root
    raise AssetSecurityError("ASSET_CACHE_DIR must resolve outside the Unity Assets directory.")


def unique_destination(destination: Path) -> tuple[Path, str | None]:
    """Allocate a deterministic non-overwriting destination path."""
    if not destination.exists():
        return destination, None
    original = destination
    counter = 1
    while True:
        candidate = destination.with_name(f"{destination.stem}-{counter}{destination.suffix}")
        if not candidate.exists():
            return candidate, str(original)
        counter += 1


def unity_file_path(unity_folder: str, path: Path, folder: Path) -> str:
    """Generate relative Unity project asset path from filesystem path and folder."""
    return f"{unity_folder}/{path.relative_to(folder).as_posix()}"


def cleanup_imported_path(path: Path) -> None:
    """Safely remove a failed import file or directory, including .meta sidecars."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
        path.with_name(f"{path.name}.meta").unlink(missing_ok=True)


async def resolve_unity_paths(bridge: Any = None) -> tuple[Path, Path]:
    """
    Resolves the Unity project root path and Assets folder path.
    Queries the Unity Editor bridge; if unreachable, falls back to local workspace conventions.
    """
    active_bridge = bridge if bridge is not None else common.bridge
    try:
        if await active_bridge.is_native_bridge():
            res = await active_bridge.get_project_paths_native()
            if res.get("success") and res.get("dataPath"):
                data_path = Path(res["dataPath"])
                project_path = Path(res.get("projectPath", data_path.parent))
                return project_path, data_path

        # Legacy fallback execution
        legacy_res = await active_bridge.execute_code(_get_project_paths_code())
        if legacy_res.get("success") and isinstance(legacy_res.get("result"), dict):
            rdata = cast(dict[str, Any], legacy_res["result"])
            data_path = Path(rdata["dataPath"])
            project_path = Path(rdata.get("projectPath", data_path.parent))
            return project_path, data_path
    except Exception as exc:
        logger.debug(f"Could not query Unity paths via bridge: {exc}")

    # Local fallback
    cwd = Path.cwd()
    if (cwd / "Assets").exists():
        return cwd, cwd / "Assets"
    return cwd, cwd / "Assets"


async def import_in_unity(
    asset_path: str,
    *,
    allow_unitypackage: bool = False,
    bridge: Any = None,
) -> list[str]:
    """Call Unity import and require concrete imported objects from either bridge implementation."""
    active_bridge = bridge if bridge is not None else common.bridge
    result = await active_bridge.execute_capability(
        _import_asset_code(asset_path, allow_unitypackage=allow_unitypackage),
        native_path="/api/visora/asset/import",
        native_payload={"assetPath": asset_path, "allowUnityPackage": allow_unitypackage},
    )
    if not result.get("success"):
        raise AssetError(result.get("error", "Unity asset import failed"))
    data = result.get("result") or result
    imported = list(data.get("importedObjects", []))
    if not imported:
        raise AssetError("Unity asset import completed without any imported objects.")
    return imported


async def instantiate_imported_asset(
    asset_path: str,
    position: ModelVector3 | None,
    rotation: ModelVector3 | None,
    scale: ModelVector3 | None,
    bridge: Any = None,
) -> tuple[str | None, int | None]:
    """Instantiate an imported asset into the scene via Unity bridge capability."""
    active_bridge = bridge if bridge is not None else common.bridge
    pos = position or [0.0, 0.0, 0.0]
    rot = rotation or [0.0, 0.0, 0.0]
    scl = scale or [1.0, 1.0, 1.0]
    result = await active_bridge.execute_capability(
        _instantiate_asset_code(asset_path, position=pos, rotation=rot, scale=scl),
        native_path="/api/visora/asset/instantiate",
        native_payload={"assetPath": asset_path, "position": pos, "rotation": rot, "scale": scl},
    )
    if not result.get("success"):
        raise AssetError(result.get("error", "Scene instantiation failed"))
    data = result.get("result") or result
    return data.get("game_object_path") or data.get("game_object_name"), data.get("instance_id")
