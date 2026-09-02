"""
Core operations for 3D asset searching, downloading, importing,
inspection, and scene instantiation.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from backend.app import mcp
from backend.config import get_settings
from backend.schemas.asset import (
    AssetSearchResultItem,
    DownloadAndImportAssetResult,
    ImportLocalAssetResult,
    InspectAssetResult,
    InstantiateSceneAssetResult,
    ModelImporterInfo,
    SearchAssetsResult,
    Vector3,
)
from backend.tools.asset import common
from backend.tools.asset.downloader import (
    download_file_stream,
    extract_filename_from_url,
    safe_extract_zip,
    sanitize_filename,
    validate_asset_extension,
    validate_unitypackage_contents,
)
from backend.tools.asset.exceptions import AssetError, AssetSecurityError
from backend.tools.asset.providers import (
    AmbientCGProvider,
    BaseAssetProvider,
    DirectUrlProvider,
    PolyPizzaProvider,
    SketchfabProvider,
)
from backend.tools.asset.scripts import (
    _get_project_paths_code,
    _import_asset_code,
    _inspect_asset_code,
    _instantiate_asset_code,
)

bridge = common.bridge
logger = common.logger

ModelVector3 = Vector3
MODEL_EXTENSIONS = {".glb", ".gltf", ".fbx", ".obj"}


def _resolve_target_folder(assets_path: Path, requested_folder: str | None) -> tuple[Path, str]:
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


def _resolve_cache_root(project_path: Path, assets_path: Path) -> Path:
    """Resolve the configured quarantine root and reject an Assets-contained cache."""
    configured = Path(get_settings().asset_cache_dir)
    cache_root = (configured if configured.is_absolute() else project_path / configured).resolve()
    try:
        cache_root.relative_to(assets_path.resolve())
    except ValueError:
        cache_root.mkdir(parents=True, exist_ok=True)
        return cache_root
    raise AssetSecurityError("ASSET_CACHE_DIR must resolve outside the Unity Assets directory.")


def _unique_destination(destination: Path) -> tuple[Path, str | None]:
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


def _unity_file_path(unity_folder: str, path: Path, folder: Path) -> str:
    return f"{unity_folder}/{path.relative_to(folder).as_posix()}"


def _cleanup_imported_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
        path.with_name(f"{path.name}.meta").unlink(missing_ok=True)


async def _import_in_unity(asset_path: str, *, allow_unitypackage: bool = False) -> list[str]:
    """Call Unity import and require concrete imported objects from either bridge implementation."""
    result = await bridge.execute_capability(
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


async def _instantiate_imported_asset(
    asset_path: str,
    position: ModelVector3 | None,
    rotation: ModelVector3 | None,
    scale: ModelVector3 | None,
) -> tuple[str | None, int | None]:
    pos = position or [0.0, 0.0, 0.0]
    rot = rotation or [0.0, 0.0, 0.0]
    scl = scale or [1.0, 1.0, 1.0]
    result = await bridge.execute_capability(
        _instantiate_asset_code(asset_path, position=pos, rotation=rot, scale=scl),
        native_path="/api/visora/asset/instantiate",
        native_payload={"assetPath": asset_path, "position": pos, "rotation": rot, "scale": scl},
    )
    if not result.get("success"):
        raise AssetError(result.get("error", "Scene instantiation failed"))
    data = result.get("result") or result
    return data.get("game_object_path") or data.get("game_object_name"), data.get("instance_id")


async def resolve_unity_paths() -> tuple[Path, Path]:
    """
    Resolves the Unity project root path and Assets folder path.
    Queries the Unity Editor bridge; if unreachable, falls back to local workspace conventions.
    """
    try:
        if await bridge.is_native_bridge():
            res = await bridge.get_project_paths_native()
            if res.get("success") and res.get("dataPath"):
                data_path = Path(res["dataPath"])
                project_path = Path(res.get("projectPath", data_path.parent))
                return project_path, data_path

        # Legacy fallback execution
        legacy_res = await bridge.execute_code(_get_project_paths_code())
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


@mcp.tool()
async def search_assets(
    query: str,
    category: str = "all",
    source: str = "auto",
    limit: int = 10,
    downloadable_only: bool = True,
) -> SearchAssetsResult:
    """
    Searches online repositories for 3D models, textures, materials, and environments.
    Supports ambientCG (free CC0 PBR textures & models), Sketchfab, Poly Pizza, and direct links.

    Args:
        query: Search keywords or direct asset URL (e.g., 'wooden chair', 'brick texture').
        category: Filter by category ('all', 'model', 'texture', 'material', 'environment').
        source: Provider filter ('auto', 'ambientcg', 'sketchfab', 'polypizza').
        limit: Maximum number of search results to return (default 10).
        downloadable_only: If True, prioritizes assets with directly resolvable download links.

    Returns:
        A SearchAssetsResult with matching assets and metadata.
    """
    warnings: list[str] = []
    items: list[AssetSearchResultItem] = []
    source_lower = source.lower().strip()

    # Direct URL quick check
    if query.strip().startswith("http://") or query.strip().startswith("https://"):
        direct_items, direct_warns = await DirectUrlProvider().search(query, category=category, limit=limit)
        return SearchAssetsResult(
            success=True,
            query=query,
            source="direct",
            total_count=len(direct_items),
            items=direct_items,
            warnings=direct_warns,
        )

    providers: list[BaseAssetProvider] = []
    if source_lower == "ambientcg":
        providers = [AmbientCGProvider()]
    elif source_lower == "sketchfab":
        providers = [SketchfabProvider()]
    elif source_lower == "polypizza":
        providers = [PolyPizzaProvider()]
    else:  # auto / all
        providers = [AmbientCGProvider(), SketchfabProvider()]
        settings = get_settings()
        if settings.poly_pizza_api_key:
            providers.append(PolyPizzaProvider())

    async def _query_provider(p: BaseAssetProvider) -> tuple[list[AssetSearchResultItem], list[str]]:
        try:
            return await p.search(query, category=category, limit=limit)
        except Exception as exc:
            return [], [f"{p.name} search exception: {exc}"]

    results = await asyncio.gather(*[_query_provider(p) for p in providers])
    for p_items, p_warns in results:
        items.extend(p_items)
        warnings.extend(p_warns)

    if downloadable_only:
        settings = get_settings()
        downloadable_items: list[AssetSearchResultItem] = []
        for item in items:
            if item.download_url:
                downloadable_items.append(item)
            elif item.source == "sketchfab" and settings.sketchfab_api_token:
                resolved_url, resolve_warnings = await SketchfabProvider().resolve_download_url(item.id)
                warnings.extend(resolve_warnings)
                if resolved_url:
                    downloadable_items.append(item)
        items = downloadable_items

    return SearchAssetsResult(
        success=True,
        query=query,
        source=source,
        total_count=len(items),
        items=items[:limit],
        warnings=warnings,
    )


@mcp.tool()
async def download_and_import_asset(  # noqa: PLR0911, PLR0912, PLR0913, PLR0915
    url: str | None = None,
    asset_id: str | None = None,
    target_folder: str | None = None,
    file_name: str | None = None,
    extract_archive: bool = True,
    allow_unitypackage: bool = False,
    instantiate_in_scene: bool = False,
    position: ModelVector3 | None = None,
    rotation: ModelVector3 | None = None,
    scale: ModelVector3 | None = None,
) -> DownloadAndImportAssetResult:
    """
    Downloads a 3D asset or texture package from a web URL, safely unpacks archives (with Zip-Slip protection),
    places files into the active Unity project, and triggers synchronous AssetDatabase import.
    Optionally instantiates the imported model into the active scene.

    Args:
        url: Direct web URL to download (.glb, .gltf, .fbx, .obj, .zip, .unitypackage).
        target_folder: Folder inside Assets/ to place the asset (default 'Assets/VisoraDownloads').
        file_name: Optional custom filename to save asset as.
        extract_archive: If True, automatically extracts ZIP archives and finds the primary model.
        instantiate_in_scene: If True, automatically instantiates the imported model into the scene.
        position: Optional [x, y, z] world coordinates for scene instantiation.
        rotation: Optional [x, y, z] Euler angles for scene instantiation.
        scale: Optional [x, y, z] scale factors for scene instantiation.

    Returns:
        A DownloadAndImportAssetResult detailing downloaded files, import status, and instantiated objects.
    """
    warnings: list[str] = []
    if bool(url) == bool(asset_id):
        return DownloadAndImportAssetResult(success=False, error="Provide exactly one of url or asset_id.")
    if asset_id:
        provider: BaseAssetProvider
        if asset_id.startswith("sketchfab:"):
            provider = SketchfabProvider()
        elif asset_id.startswith("ambientcg:"):
            provider = AmbientCGProvider()
        else:
            return DownloadAndImportAssetResult(
                success=False,
                error="asset_id must use a supported provider prefix (sketchfab: or ambientcg:).",
            )
        try:
            url, provider_warnings = await provider.resolve_download_url(asset_id)
            warnings.extend(provider_warnings)
        except Exception as exc:
            return DownloadAndImportAssetResult(success=False, error=str(exc), warnings=warnings)
        if not url:
            return DownloadAndImportAssetResult(
                success=False, error="Could not resolve asset_id to a download URL.", warnings=warnings
            )

    assert url is not None
    chosen_filename = sanitize_filename(file_name) if file_name else extract_filename_from_url(url)
    try:
        validate_asset_extension(Path(chosen_filename), allow_zip=True, allow_unitypackage=allow_unitypackage)
        project_path, assets_path = await resolve_unity_paths()
        target_dir, unity_folder = _resolve_target_folder(assets_path, target_folder)
        cache_root = _resolve_cache_root(project_path, assets_path)
    except Exception as exc:
        return DownloadAndImportAssetResult(success=False, error=str(exc), warnings=warnings)

    is_zip = Path(chosen_filename).suffix.lower() == ".zip"
    is_package = Path(chosen_filename).suffix.lower() == ".unitypackage"
    bytes_written = 0
    with tempfile.TemporaryDirectory(prefix="asset-", dir=cache_root) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        staged_file = temp_dir / chosen_filename
        try:
            bytes_written = await download_file_stream(url, staged_file)
            if is_package:
                validate_unitypackage_contents(staged_file, assets_path)
                imported_objects = await _import_in_unity(str(staged_file), allow_unitypackage=True)
                return DownloadAndImportAssetResult(
                    success=True,
                    file_size_bytes=bytes_written,
                    is_archive=True,
                    imported_objects=imported_objects,
                    warnings=warnings,
                )

            if is_zip and extract_archive:
                extracted_files = safe_extract_zip(staged_file, temp_dir / "extract")
                destination_dir, collision_source = _unique_destination(target_dir / Path(chosen_filename).stem)
                destination_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(temp_dir / "extract", destination_dir)
                primary = next(
                    (item for item in extracted_files if Path(item).suffix.lower() in MODEL_EXTENSIONS),
                    extracted_files[0],
                )
                main_asset_path = _unity_file_path(unity_folder, destination_dir / primary, target_dir)
                try:
                    imported_objects = await _import_in_unity(main_asset_path)
                    instantiated, instance_id = (
                        await _instantiate_imported_asset(main_asset_path, position, rotation, scale)
                        if instantiate_in_scene
                        else (None, None)
                    )
                except Exception:
                    _cleanup_imported_path(destination_dir)
                    raise
                if collision_source:
                    warnings.append(f"Destination existed; imported archive as {destination_dir.name}.")
                return DownloadAndImportAssetResult(
                    success=True,
                    asset_path=main_asset_path,
                    absolute_path=str((destination_dir / primary).resolve()),
                    file_size_bytes=bytes_written,
                    is_archive=True,
                    extracted_files=extracted_files,
                    imported_objects=imported_objects,
                    instantiated_game_object=instantiated,
                    instance_id=instance_id,
                    warnings=warnings,
                )

            destination, collision_source = _unique_destination(target_dir / chosen_filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_file, destination)
            main_asset_path = _unity_file_path(unity_folder, destination, target_dir)
            try:
                imported_objects = await _import_in_unity(main_asset_path)
                instantiated, instance_id = (
                    await _instantiate_imported_asset(main_asset_path, position, rotation, scale)
                    if instantiate_in_scene
                    else (None, None)
                )
            except Exception:
                _cleanup_imported_path(destination)
                raise
            if collision_source:
                warnings.append(f"Destination existed; imported asset as {destination.name}.")
            return DownloadAndImportAssetResult(
                success=True,
                asset_path=main_asset_path,
                absolute_path=str(destination.resolve()),
                file_size_bytes=bytes_written,
                is_archive=is_zip,
                imported_objects=imported_objects,
                instantiated_game_object=instantiated,
                instance_id=instance_id,
                warnings=warnings,
            )
        except Exception as exc:
            logger.warning("Asset download/import failed: %s", exc)
            return DownloadAndImportAssetResult(
                success=False, error=str(exc), file_size_bytes=bytes_written, warnings=warnings
            )


@mcp.tool()
async def import_local_asset(  # noqa: PLR0913
    source_path: str,
    target_folder: str | None = None,
    allow_unitypackage: bool = False,
    instantiate_in_scene: bool = False,
    position: ModelVector3 | None = None,
    rotation: ModelVector3 | None = None,
    scale: ModelVector3 | None = None,
) -> ImportLocalAssetResult:
    """
    Imports a local file (model, texture, prefab) into the active Unity project Assets folder,
    triggers synchronous AssetDatabase registration, and optionally instantiates it.

    Args:
        source_path: Absolute local path to the source file.
        target_folder: Destination folder inside Assets/ (default 'Assets/VisoraDownloads').
        instantiate_in_scene: If True, instantiates the asset into the active scene.
        position: Optional [x, y, z] world coordinates for instantiation.
        rotation: Optional [x, y, z] Euler angles for instantiation.
        scale: Optional [x, y, z] scale factors for instantiation.

    Returns:
        An ImportLocalAssetResult detailing the imported asset.
    """
    warnings: list[str] = []
    src = Path(source_path).resolve()
    if not src.is_file():
        return ImportLocalAssetResult(success=False, error=f"Source file not found: {source_path}")
    try:
        validate_asset_extension(src, allow_unitypackage=allow_unitypackage)
        project_path, assets_path = await resolve_unity_paths()
        target_dir, unity_folder = _resolve_target_folder(assets_path, target_folder)
        cache_root = _resolve_cache_root(project_path, assets_path)
    except Exception as exc:
        return ImportLocalAssetResult(success=False, error=str(exc))

    with tempfile.TemporaryDirectory(prefix="asset-", dir=cache_root) as temp_dir_name:
        staged_file = Path(temp_dir_name) / sanitize_filename(src.name)
        try:
            shutil.copy2(src, staged_file)
            if staged_file.suffix.lower() == ".unitypackage":
                validate_unitypackage_contents(staged_file, assets_path)
                imported_objects = await _import_in_unity(str(staged_file), allow_unitypackage=True)
                return ImportLocalAssetResult(
                    success=True,
                    file_size_bytes=staged_file.stat().st_size,
                    imported_objects=imported_objects,
                    warnings=warnings,
                )
            destination, collision_source = _unique_destination(target_dir / staged_file.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_file, destination)
            main_asset_path = _unity_file_path(unity_folder, destination, target_dir)
            try:
                imported_objects = await _import_in_unity(main_asset_path)
                instantiated, instance_id = (
                    await _instantiate_imported_asset(main_asset_path, position, rotation, scale)
                    if instantiate_in_scene
                    else (None, None)
                )
            except Exception:
                _cleanup_imported_path(destination)
                raise
            if collision_source:
                warnings.append(f"Destination existed; imported asset as {destination.name}.")
            return ImportLocalAssetResult(
                success=True,
                asset_path=main_asset_path,
                absolute_path=str(destination.resolve()),
                file_size_bytes=destination.stat().st_size,
                imported_objects=imported_objects,
                instantiated_game_object=instantiated,
                instance_id=instance_id,
                warnings=warnings,
            )
        except Exception as exc:
            logger.warning("Local asset import failed: %s", exc)
            return ImportLocalAssetResult(success=False, error=str(exc), warnings=warnings)


@mcp.tool()
async def inspect_imported_asset(asset_path: str) -> InspectAssetResult:
    """
    Inspects an imported asset in Unity, returning ModelImporter settings (animation type,
    material import mode, normal generation), submeshes, referenced materials, textures,
    and embedded animation clips.

    Args:
        asset_path: Relative Unity asset path (e.g. 'Assets/VisoraDownloads/model.glb').

    Returns:
        An InspectAssetResult with comprehensive asset and rig import metadata.
    """
    clean_path = asset_path.replace("\\", "/").strip()
    try:
        inspect_res = await bridge.execute_capability(
            _inspect_asset_code(clean_path),
            native_path="/api/visora/asset/inspect",
            native_payload={"assetPath": clean_path},
        )
        if not inspect_res.get("success"):
            return InspectAssetResult(
                success=False,
                error=inspect_res.get("error", "Asset inspection failed"),
                asset_path=clean_path,
            )

        data = inspect_res.get("result") or inspect_res

        importer_info = None
        raw_info = data.get("model_importer_info")
        if isinstance(raw_info, dict):
            importer_info = ModelImporterInfo(
                animation_type=raw_info.get("animation_type", "None"),
                clip_count=int(raw_info.get("clip_count", 0)),
                material_import_mode=raw_info.get("material_import_mode", "ImportViaMaterialDescription"),
                import_normals=bool(raw_info.get("import_normals", True)),
                global_scale=float(raw_info.get("global_scale", 1.0)),
                mesh_compression=raw_info.get("mesh_compression", "Off"),
            )

        return InspectAssetResult(
            success=True,
            asset_path=clean_path,
            asset_type=data.get("asset_type", "Unknown"),
            model_importer_info=importer_info,
            submesh_count=int(data.get("submesh_count", 0)),
            materials=list(data.get("materials", [])),
            textures=list(data.get("textures", [])),
            animation_clips=list(data.get("animation_clips", [])),
            hierarchy_tree=list(data.get("hierarchy_tree", [])),
        )
    except Exception as exc:
        logger.exception("inspect_asset_op failed")
        return InspectAssetResult(
            success=False,
            error=str(exc),
            asset_path=clean_path,
        )


@mcp.tool()
async def instantiate_scene_asset(  # noqa: PLR0913
    asset_path: str,
    parent_path: str | None = None,
    position: ModelVector3 | None = None,
    rotation: ModelVector3 | None = None,
    scale: ModelVector3 | None = None,
    name: str | None = None,
) -> InstantiateSceneAssetResult:
    """
    Instantiates an existing asset or prefab from the Unity project into the active scene
    with full Undo registration.

    Args:
        asset_path: Relative Unity asset path to instantiate (e.g. 'Assets/Models/Prop.prefab').
        parent_path: Optional hierarchy path of parent GameObject.
        position: World position coordinates [x, y, z] (default [0, 0, 0]).
        rotation: Euler angles [x, y, z] (default [0, 0, 0]).
        scale: Scale factors [x, y, z] (default [1, 1, 1]).
        name: Optional custom name for the instantiated GameObject.

    Returns:
        An InstantiateSceneAssetResult with the instantiated GameObject path and instance ID.
    """
    clean_path = asset_path.replace("\\", "/").strip()
    pos = position or [0.0, 0.0, 0.0]
    rot = rotation or [0.0, 0.0, 0.0]
    scl = scale or [1.0, 1.0, 1.0]

    try:
        inst_res = await bridge.execute_capability(
            _instantiate_asset_code(
                clean_path,
                parent_path=parent_path,
                position=pos,
                rotation=rot,
                scale=scl,
                name=name,
            ),
            native_path="/api/visora/asset/instantiate",
            native_payload={
                "assetPath": clean_path,
                "parentPath": parent_path or "",
                "position": pos,
                "rotation": rot,
                "scale": scl,
                "name": name or "",
            },
        )
        if not inst_res.get("success"):
            return InstantiateSceneAssetResult(
                success=False,
                error=inst_res.get("error", "Instantiation failed"),
            )

        data = inst_res.get("result") or inst_res
        return InstantiateSceneAssetResult(
            success=True,
            game_object_name=data.get("game_object_name"),
            game_object_path=data.get("game_object_path"),
            instance_id=data.get("instance_id"),
            world_position=list(data.get("world_position", pos)),
        )
    except Exception as exc:
        logger.exception("instantiate_scene_asset_op failed")
        return InstantiateSceneAssetResult(
            success=False,
            error=str(exc),
        )


# Backward-compatible aliases
search_assets_op = search_assets
download_and_import_asset_op = download_and_import_asset
import_local_asset_op = import_local_asset
inspect_asset_op = inspect_imported_asset
instantiate_scene_asset_op = instantiate_scene_asset
