"""Read-only inspection of Prefab assets, without instantiating them into the active scene."""

from typing import Any

import backend.tools.prefab as prefab_pkg
from backend.app import mcp
from backend.config import get_settings
from backend.schemas.prefab import (
    InspectPrefabAssetResult,
    PrefabComponentInfo,
    PrefabNestedInstance,
    PrefabObjectNode,
)
from backend.tools.errors import bridge_error, bridge_retry_fields
from backend.tools.payload import coerce_literal, warns
from backend.tools.prefab.common import bridge_supports, logger

_CAPABILITY = "prefab_asset_inspection"
_READY_TIMEOUT_SECONDS = 15.0

_PREFAB_KINDS = {"regular", "variant", "model"}
_CONNECTION_STATUSES = {"connected", "missing_asset", "disconnected", "not_an_instance"}

# Unity registers Prefab-shaped GameObject assets from exactly two sources: authored `.prefab`
# files, and model files whose importer produces a Model Prefab. Anything else (a Material, a
# Texture, an AnimationClip, a folder) has no Prefab hierarchy at all, so it is rejected here with
# a distinct error rather than sent to Unity to fail generically.
_PREFAB_EXTENSION = ".prefab"
_MODEL_EXTENSIONS = frozenset(
    {".fbx", ".obj", ".dae", ".blend", ".gltf", ".glb", ".3ds", ".dxf", ".max", ".c4d", ".ma", ".mb"}
)
_PROJECT_ROOTS = ("Assets/", "Packages/")


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _normalize_asset_path(asset_path: str) -> tuple[str, str | None]:
    """
    Normalize a caller-supplied asset path and reject anything that is not a project Prefab asset.

    Returns `(normalized_path, error)`. The normalized path is returned even on failure so the
    result can echo back what was actually evaluated.
    """
    raw = str(asset_path) if asset_path is not None else ""
    clean = raw.replace("\\", "/").strip().rstrip("/")
    while "//" in clean:
        clean = clean.replace("//", "/")

    if not clean:
        return clean, "asset_path is required."
    if clean.startswith("/") or (len(clean) > 1 and clean[1] == ":"):
        return clean, f"asset_path must be project-relative, not an absolute filesystem path: '{clean}'."
    if any(segment == ".." for segment in clean.split("/")):
        return clean, f"asset_path must not traverse outside the Unity project: '{clean}'."
    if not clean.startswith(_PROJECT_ROOTS):
        return clean, f"asset_path must live under Assets/ or Packages/ in the Unity project: '{clean}'."

    suffix = clean[clean.rfind(".") :].lower() if "." in clean.rsplit("/", 1)[-1] else ""
    if suffix != _PREFAB_EXTENSION and suffix not in _MODEL_EXTENSIONS:
        return clean, (
            f"asset_path is not a Prefab-compatible asset: '{clean}'. Expected a '.prefab' file or an "
            f"imported model file ({', '.join(sorted(_MODEL_EXTENSIONS))})."
        )
    return clean, None


def _components(raw: Any, warnings: list[str], node_path: str) -> list[PrefabComponentInfo]:
    """Build the component list of one node, tolerating a malformed entry rather than failing the call."""
    if not isinstance(raw, list):
        if raw is not None:
            warnings.append(f"Ignored non-list components on '{node_path}'.")
        return []
    components: list[PrefabComponentInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append(f"Ignored a malformed component entry on '{node_path}'.")
            continue
        type_name = str(item.get("typeName") or "").strip() or "UnknownComponent"
        components.append(
            PrefabComponentInfo(
                type_name=type_name,
                is_missing_script=bool(item.get("isMissingScript", False)),
            )
        )
    return components


def _hierarchy(raw: Any, warnings: list[str]) -> list[PrefabObjectNode]:
    if not isinstance(raw, list):
        if raw is not None:
            warnings.append("Ignored non-list hierarchy payload from the Unity bridge.")
        return []
    nodes: list[PrefabObjectNode] = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append("Ignored a malformed hierarchy entry from the Unity bridge.")
            continue
        relative_path = str(item.get("relativePath", ""))
        nested_source = item.get("nestedSourceAssetPath")
        nested_source_str = str(nested_source).replace("\\", "/").strip() if nested_source else None
        nodes.append(
            PrefabObjectNode(
                relative_path=relative_path,
                name=str(item.get("name", "")),
                depth=_safe_int(item.get("depth"), 0),
                active_self=bool(item.get("activeSelf", True)),
                components=_components(item.get("components"), warnings, relative_path),
                is_nested_prefab_instance_root=bool(item.get("isNestedPrefabInstanceRoot", False)),
                nested_source_asset_path=nested_source_str,
            )
        )
    return nodes


def _nested_prefabs(raw: Any, warnings: list[str]) -> list[PrefabNestedInstance]:
    if not isinstance(raw, list):
        if raw is not None:
            warnings.append("Ignored non-list nested prefabs payload from the Unity bridge.")
        return []
    nested: list[PrefabNestedInstance] = []
    for item in raw:
        if not isinstance(item, dict):
            warnings.append("Ignored a malformed nested prefab entry from the Unity bridge.")
            continue
        source_path = item.get("sourceAssetPath")
        source_path_str = str(source_path).replace("\\", "/").strip() if source_path else None
        source_guid = item.get("sourceGuid")
        source_guid_str = str(source_guid).strip() if source_guid else None
        nested.append(
            PrefabNestedInstance(
                relative_path=str(item.get("relativePath", "")),
                name=str(item.get("name", "")),
                source_asset_path=source_path_str,
                source_guid=source_guid_str,
                connection_status=coerce_literal(
                    item.get("connectionStatus"),
                    _CONNECTION_STATUSES,
                    warnings,
                    field="nested prefab connection status",
                ),
            )
        )
    return nested


def _build_result(asset_path: str, resp: dict[str, Any], limit: int) -> InspectPrefabAssetResult:
    """Translate a native bridge payload into the typed result, never inventing success."""
    warnings = warns(resp)

    if not resp.get("success"):
        return InspectPrefabAssetResult(
            success=False,
            error=str(resp.get("error") or "Prefab asset inspection failed."),
            asset_path=str(resp.get("assetPath") or asset_path),
            warnings=warnings,
        )

    hierarchy = _hierarchy(resp.get("hierarchy"), warnings)
    nested = _nested_prefabs(resp.get("nestedPrefabs"), warnings)
    truncated = bool(resp.get("truncated", False))

    # Second-line defence: a bridge that ignores maxObjects must not be able to flood the agent's
    # context. Unity normally truncates first and sets `truncated` itself.
    if len(hierarchy) > limit:
        hierarchy = hierarchy[:limit]
        truncated = True
        warnings.append(f"Hierarchy was capped locally at {limit} nodes; the bridge returned more.")

    if not hierarchy:
        return InspectPrefabAssetResult(
            success=False,
            error="Unity reported a successful inspection but returned no Prefab hierarchy.",
            asset_path=asset_path,
            warnings=warnings,
        )

    base_prefab = resp.get("basePrefabPath")
    base_prefab_str = str(base_prefab).replace("\\", "/").strip() if base_prefab else None

    raw_targets = resp.get("editTargetAssetPaths")
    edit_targets: list[str] = []
    if isinstance(raw_targets, list):
        for p in raw_targets:
            if p and str(p).strip():
                clean_target = str(p).replace("\\", "/").strip()
                if clean_target not in edit_targets:
                    edit_targets.append(clean_target)
        edit_targets.sort()

    total_obj = _safe_int(resp.get("totalObjectCount"), len(hierarchy))
    total_comp = _safe_int(resp.get("totalComponentCount"), sum(len(n.components) for n in hierarchy))

    return InspectPrefabAssetResult(
        success=True,
        asset_path=str(resp.get("assetPath") or asset_path),
        prefab_name=str(resp.get("prefabName", "")),
        guid=str(resp.get("assetGuid", "")),
        prefab_kind=coerce_literal(resp.get("prefabKind"), _PREFAB_KINDS, warnings, field="prefab kind"),
        base_prefab_path=base_prefab_str,
        root_object_name=str(resp.get("rootObjectName", "")),
        root_connection_status=coerce_literal(
            resp.get("rootConnectionStatus"),
            _CONNECTION_STATUSES,
            warnings,
            field="root connection status",
        ),
        hierarchy=hierarchy,
        nested_prefabs=nested,
        edit_target_asset_paths=edit_targets,
        total_object_count=total_obj,
        total_component_count=total_comp,
        truncated=truncated,
        warnings=warnings,
    )


@mcp.tool()
async def inspect_prefab_asset(asset_path: str) -> InspectPrefabAssetResult:
    """
    Inspects a Prefab asset directly on disk - its kind, hierarchy, components, and nesting - without
    instantiating it in the active scene and without opening a Prefab Stage.

    Unity loads the Prefab into an isolated preview context that is always unloaded afterwards, so
    the active scene, its dirty state, the current selection, and any open Prefab Stage are left
    untouched. Requires Edit Mode. Reports the Variant base Prefab, every nested Prefab instance and
    its source asset, and the unique set of Prefab assets a later edit could target.

    Args:
        asset_path: Project-relative path of a '.prefab' file or an imported model file
            (e.g. 'Assets/Prefabs/Enemy.prefab').

    Returns:
        An InspectPrefabAssetResult with the Prefab kind, hierarchy, components, nesting, and edit targets.
    """
    clean_path, path_error = _normalize_asset_path(asset_path)
    if path_error is not None:
        return InspectPrefabAssetResult(success=False, error=path_error, asset_path=clean_path)

    if not await bridge_supports(_CAPABILITY):
        return InspectPrefabAssetResult(
            success=False,
            error=(
                f"Unity bridge does not support capability '{_CAPABILITY}'. Prefab asset inspection "
                "requires the Visora Unity package; update it or switch UNITY_BRIDGE_MODE to native."
            ),
            asset_path=clean_path,
        )

    try:
        editor_state = await prefab_pkg.bridge.wait_for_editor_ready(timeout_seconds=_READY_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("Unity did not become idle before prefab inspection: %s", exc)
        return InspectPrefabAssetResult(**bridge_error(exc), asset_path=clean_path)

    if bool(editor_state.get("isPlaying", False)):
        return InspectPrefabAssetResult(
            success=False,
            error="Prefab asset inspection requires Edit Mode; exit Play Mode and retry.",
            asset_path=clean_path,
        )

    limit = max(1, get_settings().prefab_max_hierarchy_nodes)
    try:
        resp = await prefab_pkg.bridge.inspect_prefab_asset_native(asset_path=clean_path, max_objects=limit)
    except Exception as exc:
        logger.exception("inspect_prefab_asset failed")
        return InspectPrefabAssetResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            **bridge_retry_fields(exc),
            asset_path=clean_path,
        )

    return _build_result(clean_path, resp, limit)
