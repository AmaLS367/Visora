"""
Core operations for 3D asset searching, downloading, importing,
inspection, and scene instantiation.
"""

from __future__ import annotations

import asyncio
import shutil
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
)
from backend.tools.asset import common
from backend.tools.asset.downloader import (
    download_file_stream,
    extract_filename_from_url,
    safe_extract_zip,
    sanitize_filename,
)
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
        # Prioritize items with direct download URLs or resolved download capability
        items = sorted(items, key=lambda x: (x.download_url is not None, x.category == "model"), reverse=True)

    return SearchAssetsResult(
        success=True,
        query=query,
        source=source,
        total_count=len(items),
        items=items[:limit],
        warnings=warnings,
    )


@mcp.tool()
async def download_and_import_asset(  # noqa: PLR0913, PLR0912, PLR0915
    url: str,
    target_folder: str = "Assets/VisoraDownloads",
    file_name: str | None = None,
    extract_archive: bool = True,
    instantiate_in_scene: bool = False,
    position: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
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
    _, assets_path = await resolve_unity_paths()

    # Determine filename and target path
    chosen_filename = sanitize_filename(file_name) if file_name else extract_filename_from_url(url)
    clean_target_folder = target_folder.replace("\\", "/").strip("/")
    if not clean_target_folder.startswith("Assets"):
        clean_target_folder = f"Assets/{clean_target_folder}"

    # Folder relative to project root
    folder_rel = clean_target_folder[len("Assets") :].lstrip("/")
    abs_target_dir = assets_path / folder_rel if folder_rel else assets_path
    abs_target_dir.mkdir(parents=True, exist_ok=True)

    download_target_path = abs_target_dir / chosen_filename

    try:
        bytes_written = await download_file_stream(url, download_target_path)
    except Exception as exc:
        logger.exception(f"Asset download failed: {exc}")
        return DownloadAndImportAssetResult(
            success=False,
            error=str(exc),
            warnings=warnings,
        )

    is_archive = download_target_path.suffix.lower() == ".zip"
    extracted_files: list[str] = []
    main_asset_rel_path = f"{clean_target_folder}/{chosen_filename}"

    if is_archive and extract_archive:
        # Extract to a subfolder named after the archive without extension
        archive_stem = download_target_path.stem
        extract_dir = abs_target_dir / archive_stem
        try:
            extracted_files = safe_extract_zip(download_target_path, extract_dir)
            # Find a 3D model or primary texture in extracted files
            model_exts = {".glb", ".gltf", ".fbx", ".obj"}
            chosen_primary: str | None = None
            for ef in extracted_files:
                p = Path(ef)
                if p.suffix.lower() in model_exts:
                    chosen_primary = ef
                    break
            if not chosen_primary and extracted_files:
                chosen_primary = extracted_files[0]

            if chosen_primary:
                main_asset_rel_path = f"{clean_target_folder}/{archive_stem}/{chosen_primary}"
            else:
                main_asset_rel_path = f"{clean_target_folder}/{archive_stem}"

        except Exception as exc:
            warnings.append(f"Archive extraction failed: {exc}")
            logger.warning(f"Archive extraction failed: {exc}")

    # Import asset in Unity
    imported_objects: list[str] = []
    try:
        import_res = await bridge.execute_capability(
            _import_asset_code(main_asset_rel_path),
            native_path="/api/visora/asset/import",
            native_payload={"assetPath": main_asset_rel_path},
        )
        if import_res.get("success"):
            r_data = import_res.get("result") or import_res
            imported_objects = list(r_data.get("importedObjects", [main_asset_rel_path]))
        else:
            warnings.append(f"Unity asset import reported failure: {import_res.get('error')}")
    except Exception as exc:
        warnings.append(f"Unity bridge import call failed: {exc}")
        logger.warning(f"Unity bridge import call failed: {exc}")

    # Optional scene instantiation
    instantiated_go: str | None = None
    instance_id: int | None = None
    if instantiate_in_scene:
        try:
            pos = position or [0.0, 0.0, 0.0]
            rot = rotation or [0.0, 0.0, 0.0]
            scl = scale or [1.0, 1.0, 1.0]

            inst_res = await bridge.execute_capability(
                _instantiate_asset_code(main_asset_rel_path, position=pos, rotation=rot, scale=scl),
                native_path="/api/visora/asset/instantiate",
                native_payload={
                    "assetPath": main_asset_rel_path,
                    "position": pos,
                    "rotation": rot,
                    "scale": scl,
                },
            )
            if inst_res.get("success"):
                idata = inst_res.get("result") or inst_res
                instantiated_go = idata.get("game_object_path") or idata.get("game_object_name")
                instance_id = idata.get("instance_id")
            else:
                warnings.append(f"Scene instantiation failed: {inst_res.get('error')}")
        except Exception as exc:
            warnings.append(f"Failed to instantiate asset in scene: {exc}")

    return DownloadAndImportAssetResult(
        success=True,
        asset_path=main_asset_rel_path,
        absolute_path=str(download_target_path.resolve()),
        file_size_bytes=bytes_written,
        is_archive=is_archive,
        extracted_files=extracted_files,
        imported_objects=imported_objects or [main_asset_rel_path],
        instantiated_game_object=instantiated_go,
        instance_id=instance_id,
        warnings=warnings,
    )


@mcp.tool()
async def import_local_asset(  # noqa: PLR0913
    source_path: str,
    target_folder: str = "Assets/VisoraDownloads",
    instantiate_in_scene: bool = False,
    position: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
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
    src = Path(source_path)
    if not src.exists() or not src.is_file():
        return ImportLocalAssetResult(
            success=False,
            error=f"Source file not found: {source_path}",
        )

    _, assets_path = await resolve_unity_paths()
    clean_target_folder = target_folder.replace("\\", "/").strip("/")
    if not clean_target_folder.startswith("Assets"):
        clean_target_folder = f"Assets/{clean_target_folder}"

    folder_rel = clean_target_folder[len("Assets") :].lstrip("/")
    abs_target_dir = assets_path / folder_rel if folder_rel else assets_path
    abs_target_dir.mkdir(parents=True, exist_ok=True)

    dest_file = abs_target_dir / src.name
    shutil.copy2(src, dest_file)
    file_size = dest_file.stat().st_size

    main_asset_rel_path = f"{clean_target_folder}/{src.name}"

    imported_objects: list[str] = []
    try:
        import_res = await bridge.execute_capability(
            _import_asset_code(main_asset_rel_path),
            native_path="/api/visora/asset/import",
            native_payload={"assetPath": main_asset_rel_path},
        )
        if import_res.get("success"):
            r_data = import_res.get("result") or import_res
            imported_objects = list(r_data.get("importedObjects", [main_asset_rel_path]))
        else:
            warnings.append(f"AssetDatabase import warning: {import_res.get('error')}")
    except Exception as exc:
        warnings.append(f"Unity bridge import call failed: {exc}")

    instantiated_go: str | None = None
    instance_id: int | None = None
    if instantiate_in_scene:
        try:
            pos = position or [0.0, 0.0, 0.0]
            rot = rotation or [0.0, 0.0, 0.0]
            scl = scale or [1.0, 1.0, 1.0]

            inst_res = await bridge.execute_capability(
                _instantiate_asset_code(main_asset_rel_path, position=pos, rotation=rot, scale=scl),
                native_path="/api/visora/asset/instantiate",
                native_payload={
                    "assetPath": main_asset_rel_path,
                    "position": pos,
                    "rotation": rot,
                    "scale": scl,
                },
            )
            if inst_res.get("success"):
                idata = inst_res.get("result") or inst_res
                instantiated_go = idata.get("game_object_path") or idata.get("game_object_name")
                instance_id = idata.get("instance_id")
            else:
                warnings.append(f"Instantiation failed: {inst_res.get('error')}")
        except Exception as exc:
            warnings.append(f"Failed to instantiate asset: {exc}")

    return ImportLocalAssetResult(
        success=True,
        asset_path=main_asset_rel_path,
        absolute_path=str(dest_file.resolve()),
        file_size_bytes=file_size,
        imported_objects=imported_objects or [main_asset_rel_path],
        instantiated_game_object=instantiated_go,
        instance_id=instance_id,
        warnings=warnings,
    )


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
    position: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
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
