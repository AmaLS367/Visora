"""Read-only, typed override diff between a scene Prefab instance and its source Prefab asset."""

import re
from collections import Counter
from typing import Any, Literal

from pydantic import ValidationError

import backend.tools.prefab as prefab_pkg
from backend.app import mcp
from backend.schemas.prefab import (
    InspectPrefabOverridesResult,
    PrefabObjectReference,
    PrefabOverride,
    PrefabOverrideCounts,
    PrefabPathCandidate,
    PrefabPropertyValue,
)
from backend.tools.errors import bridge_retry_fields
from backend.tools.payload import coerce_literal, safe_int, warns
from backend.tools.prefab.common import logger, native_preflight, normalize_hierarchy_path, optional_asset_path

_CAPABILITY = "prefab_override_inspection"
_OPERATION = "Prefab override inspection"

_SCOPES = ("nearest", "outermost")
_MAX_OVERRIDES_CEILING = 1000
_OVERRIDE_ID = re.compile(r"^ovr_[0-9a-f]{16}$")

_CATEGORIES = {
    "modified_property",
    "added_component",
    "removed_component",
    "added_game_object",
    "removed_game_object",
}
_VALUE_KINDS = {"integer", "float", "boolean", "string", "enum", "array_size", "object_reference", "other"}
_PREFAB_KINDS = {"regular", "variant", "model", "unknown"}
_CONNECTION_STATUSES = {"connected", "missing_asset", "disconnected", "not_an_instance", "unknown"}

# Wire key of each category's count, in the category order Unity sorts by.
_COUNT_KEYS = {
    "modified_property": "modifiedProperty",
    "added_component": "addedComponent",
    "removed_component": "removedComponent",
    "added_game_object": "addedGameObject",
    "removed_game_object": "removedGameObject",
}


class _MalformedEntryError(ValueError):
    """One override entry that cannot be trusted; the whole diff is then incomplete."""


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _reference(raw: Any) -> PrefabObjectReference | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _MalformedEntryError("object reference is not an object")
    return PrefabObjectReference(
        is_null=bool(raw.get("isNull", False)),
        type_name=_optional_str(raw.get("typeName")),
        name=_optional_str(raw.get("name")),
        asset_path=optional_asset_path(raw.get("assetPath")),
        guid=_optional_str(raw.get("assetGuid")) or None,
        local_file_id=_optional_int(raw.get("localFileId")),
        scene_path=_optional_str(raw.get("scenePath")) or None,
        hierarchy_path=_optional_str(raw.get("hierarchyPath")),
    )


def _value(raw: Any, warnings: list[str]) -> PrefabPropertyValue | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _MalformedEntryError("property value is not an object")
    scalar = raw.get("value")
    if scalar is not None and not isinstance(scalar, bool | int | float | str):
        raise _MalformedEntryError("property value is not a scalar")
    kind = coerce_literal(raw.get("kind"), _VALUE_KINDS, warnings, field="property value kind", fallback="other")
    return PrefabPropertyValue(kind=kind, value=scalar, object_reference=_reference(raw.get("objectReference")))


def _override(raw: Any, warnings: list[str]) -> PrefabOverride:
    """Parse one entry strictly: an ID an agent cannot trust must never reach it."""
    if not isinstance(raw, dict):
        raise _MalformedEntryError("entry is not an object")
    override_id = raw.get("overrideId")
    if not isinstance(override_id, str) or not _OVERRIDE_ID.match(override_id):
        raise _MalformedEntryError(f"invalid override ID {override_id!r}")
    category = raw.get("category")
    if category not in _CATEGORIES:
        raise _MalformedEntryError(f"unknown category {category!r} on {override_id}")

    raw_targets = raw.get("targetAssetPaths")
    if raw_targets is not None and not isinstance(raw_targets, list):
        raise _MalformedEntryError(f"non-list target assets on {override_id}")
    targets: list[str] = []
    for item in raw_targets or []:
        clean = optional_asset_path(item)
        # Chain order (immediate source inwards) is meaningful, so it is kept rather than sorted.
        if clean and clean not in targets:
            targets.append(clean)

    try:
        return PrefabOverride(
            override_id=override_id,
            category=category,
            object_path=_optional_str(raw.get("objectPath")),
            source_object_path=_optional_str(raw.get("sourceObjectPath")),
            component_type=_optional_str(raw.get("componentType")),
            component_ordinal=_optional_int(raw.get("componentOrdinal")),
            property_path=_optional_str(raw.get("propertyPath")),
            source_value=_value(raw.get("sourceValue"), warnings),
            instance_value=_value(raw.get("instanceValue"), warnings),
            is_default_override=bool(raw.get("isDefaultOverride", False)),
            target_asset_paths=targets,
            recommended_target_asset_path=optional_asset_path(raw.get("recommendedTargetAssetPath")),
            applicable=bool(raw.get("applicable", False)),
            not_applicable_reason=_optional_str(raw.get("notApplicableReason")),
            id_collision=bool(raw.get("idCollision", False)),
            description=str(raw.get("description") or ""),
        )
    except ValidationError as exc:
        raise _MalformedEntryError(f"invalid fields on {override_id}: {exc.error_count()} error(s)") from exc


def _counts(raw: Any) -> PrefabOverrideCounts | None:
    if not isinstance(raw, dict):
        return None
    values: dict[str, int] = {}
    for field, key in _COUNT_KEYS.items():
        count = safe_int(raw.get(key), -1)
        if count < 0:
            return None
        values[field] = count
    return PrefabOverrideCounts(**values)


def _candidates(raw: Any) -> list[PrefabPathCandidate]:
    if not isinstance(raw, list):
        return []
    return [
        PrefabPathCandidate(
            scene_path=_optional_str(item.get("scenePath")) or None,
            hierarchy_path=str(item["hierarchyPath"]),
        )
        for item in raw
        if isinstance(item, dict) and item.get("hierarchyPath")
    ]


def _mark_unaddressable(entry: PrefabOverride, reason: str) -> None:
    entry.applicable = False
    entry.target_asset_paths = []
    entry.recommended_target_asset_path = None
    entry.not_applicable_reason = reason


def _audit_overrides(overrides: list[PrefabOverride], warnings: list[str]) -> None:
    """
    Second-line checks on what Unity asserted: every ID unique, every applicable override backed by
    a target, every recommendation one of the targets. Violations downgrade the entry, never upgrade.
    """
    duplicates = {override_id for override_id, count in Counter(o.override_id for o in overrides).items() if count > 1}
    for entry in overrides:
        if entry.override_id in duplicates or entry.id_collision:
            if entry.override_id in duplicates and not entry.id_collision:
                warnings.append(f"Override ID '{entry.override_id}' appears more than once in the Unity response.")
            entry.id_collision = True
            _mark_unaddressable(
                entry,
                entry.not_applicable_reason
                or (
                    f"Override ID '{entry.override_id}' is not unique within this instance, so it cannot address "
                    "this change safely."
                ),
            )
            continue

        if entry.applicable and not entry.target_asset_paths:
            warnings.append(f"Override '{entry.override_id}' was marked applicable without any target asset.")
            _mark_unaddressable(entry, "Unity reported no Prefab asset that can accept this override.")
            continue

        if entry.recommended_target_asset_path and entry.recommended_target_asset_path not in entry.target_asset_paths:
            warnings.append(
                f"Override '{entry.override_id}' recommended '{entry.recommended_target_asset_path}', which is not "
                "one of its target assets; the recommendation was dropped."
            )
            entry.recommended_target_asset_path = None

        if not entry.applicable and not entry.not_applicable_reason:
            entry.not_applicable_reason = "Unity did not report a Prefab asset that can accept this override."


def _parse_overrides(raw: Any, warnings: list[str]) -> tuple[list[PrefabOverride], str | None]:
    """Every entry parses or the diff is reported incomplete - a partial list is never passed on."""
    if not isinstance(raw, list):
        return [], "Unity reported a successful inspection but returned no override list."

    overrides: list[PrefabOverride] = []
    problems: list[str] = []
    for index, item in enumerate(raw):
        try:
            overrides.append(_override(item, warnings))
        except _MalformedEntryError as exc:
            problems.append(f"#{index}: {exc}")
    if problems:
        noun = "entry" if len(problems) == 1 else "entries"
        return [], (
            f"Unity returned {len(problems)} malformed override {noun} ({'; '.join(problems[:3])}); "
            "the override diff is incomplete."
        )
    return overrides, None


def _checked_totals(resp: dict[str, Any], listed: int, truncated: bool) -> tuple[PrefabOverrideCounts, int, str | None]:
    """Unity's totals, cross-checked against each other and against what was actually listed."""
    counts = _counts(resp.get("overrideCounts"))
    total = safe_int(resp.get("totalOverrideCount"), -1)
    if counts is None or total < 0:
        return PrefabOverrideCounts(), 0, "Unity did not report override totals; the override diff is incomplete."
    if counts.total() != total:
        return (
            counts,
            total,
            (f"Unity's per-category override counts ({counts.total()}) do not add up to its total ({total})."),
        )
    if listed > total or (not truncated and listed != total):
        return (
            counts,
            total,
            (
                f"Unity listed {listed} overrides but reported a total of {total}"
                f"{' with' if truncated else ' without'} truncation; the override diff is inconsistent."
            ),
        )
    return counts, total, None


def _drop_leaked_defaults(
    overrides: list[PrefabOverride], counts: PrefabOverrideCounts, warnings: list[str]
) -> tuple[list[PrefabOverride], int]:
    """
    Second-line default filtering: a bridge that ignored includeDefaultOverrides=false must not push
    default overrides into the diff an agent later selects from. Adjusts `counts` in place.
    """
    leaked = [entry for entry in overrides if entry.is_default_override]
    if not leaked:
        return overrides, 0
    for entry in leaked:
        setattr(counts, entry.category, max(0, getattr(counts, entry.category) - 1))
    warnings.append(f"Removed {len(leaked)} default override(s) the bridge returned despite the filter.")
    return [entry for entry in overrides if not entry.is_default_override], len(leaked)


def _context_fields(resp: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Instance and source identity, reported on failures too so an agent sees what was resolved."""
    return {
        "scene_path": _optional_str(resp.get("scenePath")) or None,
        "instance_root_path": _optional_str(resp.get("instanceRootPath")) or None,
        "outermost_instance_root_path": _optional_str(resp.get("outermostInstanceRootPath")) or None,
        "source_asset_path": optional_asset_path(resp.get("sourceAssetPath")),
        "source_guid": _optional_str(resp.get("sourceGuid")) or None,
        "prefab_kind": coerce_literal(resp.get("prefabKind", "unknown"), _PREFAB_KINDS, warnings, field="prefab kind"),
        "connection_status": coerce_literal(
            resp.get("connectionStatus", "unknown"), _CONNECTION_STATUSES, warnings, field="connection status"
        ),
        "warnings": warnings,
    }


def _build_result(
    *,
    instance_path: str,
    scope: str,
    include_default_overrides: bool,
    resp: dict[str, Any],
    limit: int,
) -> InspectPrefabOverridesResult:
    """Translate a native bridge payload into the typed result; an incomplete diff is a failure."""
    warnings = warns(resp)
    context: dict[str, Any] = {
        "instance_path": instance_path,
        "scope": scope,
        "include_default_overrides": include_default_overrides,
        **_context_fields(resp, warnings),
    }

    if not resp.get("success"):
        return InspectPrefabOverridesResult(
            success=False,
            error=str(resp.get("error") or "Prefab override inspection failed."),
            path_candidates=_candidates(resp.get("pathCandidates")),
            **context,
        )

    truncated = bool(resp.get("truncated", False))
    overrides, error = _parse_overrides(resp.get("overrides"), warnings)
    counts, total, totals_error = _checked_totals(resp, len(overrides), truncated)
    if not context.get("instance_root_path"):
        error = "Unity reported a successful inspection but did not identify the Prefab instance root."
    if not context.get("source_asset_path"):
        error = error or "Unity reported a successful inspection but did not identify the source Prefab asset."
    error = error or totals_error
    if error is not None:
        return InspectPrefabOverridesResult(success=False, error=error, **context)

    excluded_defaults = max(0, safe_int(resp.get("excludedDefaultOverrideCount"), 0))
    if not include_default_overrides:
        overrides, dropped = _drop_leaked_defaults(overrides, counts, warnings)
        total = max(0, total - dropped)
        excluded_defaults += dropped

    _audit_overrides(overrides, warnings)

    if len(overrides) > limit:
        overrides = overrides[:limit]
        truncated = True
        warnings.append(f"Overrides were capped locally at {limit}; the bridge returned more.")

    return InspectPrefabOverridesResult(
        success=True,
        total_override_count=total,
        override_counts=counts,
        excluded_default_override_count=excluded_defaults,
        truncated=truncated,
        overrides=overrides,
        **context,
    )


def _request_error(scope: Any, include_default_overrides: Any, max_overrides: Any) -> str | None:
    """Validate the non-path parameters; MCP clients are schema-checked, direct callers are not."""
    if scope not in _SCOPES:
        return f"scope must be 'nearest' or 'outermost', got {scope!r}."
    if not isinstance(include_default_overrides, bool):
        return f"include_default_overrides must be a boolean, got {include_default_overrides!r}."
    if (
        isinstance(max_overrides, bool)
        or not isinstance(max_overrides, int)
        or not 1 <= max_overrides <= _MAX_OVERRIDES_CEILING
    ):
        return f"max_overrides must be an integer between 1 and {_MAX_OVERRIDES_CEILING}, got {max_overrides!r}."
    return None


@mcp.tool()
async def inspect_prefab_overrides(
    instance_path: str,
    include_default_overrides: bool = False,
    scope: Literal["nearest", "outermost"] = "nearest",
    max_overrides: int = 200,
    scene_path: str | None = None,
) -> InspectPrefabOverridesResult:
    """
    Read-only typed diff between a Prefab instance in a loaded scene and its source Prefab asset.

    Reports modified properties (with source and instance values and structured object references),
    added and removed components, and added and removed child GameObjects. Each override carries a
    stable `override_id`, the editable Prefab assets it could be applied to, a recommended target,
    and whether (and why not) it is applicable. Nothing is applied, reverted, saved, or selected.
    Requires Edit Mode and the native Visora Unity package.

    Args:
        instance_path: Root-anchored hierarchy path of any GameObject inside the Prefab instance
            (e.g. 'Level/Enemy/Weapon'). Segments may be indexed like 'Arm[1]' to pick one of several
            same-name siblings; an ambiguous or missing path is an error listing candidates.
        include_default_overrides: Include Unity default overrides (root position/rotation/name),
            which Unity never applies to an asset. Off by default.
        scope: 'nearest' anchors the diff to the closest Prefab instance root (for example a nested
            Prefab); 'outermost' to the top-level instance root in the scene.
        max_overrides: Maximum overrides listed (1-1000); totals always describe the full diff.
        scene_path: Restrict the lookup to one loaded scene, by asset path or name.

    Returns:
        An InspectPrefabOverridesResult with the resolved instance root, source asset, totals, and overrides.
    """
    clean_path, path_error = normalize_hierarchy_path(instance_path)
    safe_scope = scope if scope in _SCOPES else "nearest"
    clean_scene = optional_asset_path(scene_path)

    def rejected(**failure: Any) -> InspectPrefabOverridesResult:
        """A failed result echoing the request; `failure` carries `error` and any retry hints."""
        return InspectPrefabOverridesResult(
            success=False,
            instance_path=clean_path,
            scope=safe_scope,
            include_default_overrides=include_default_overrides is True,
            scene_path=clean_scene,
            **{key: value for key, value in failure.items() if key != "success"},
        )

    input_error = path_error or _request_error(scope, include_default_overrides, max_overrides)
    if input_error is not None:
        return rejected(error=input_error)

    failure = await native_preflight(_CAPABILITY, _OPERATION)
    if failure is not None:
        return rejected(**failure)

    try:
        resp = await prefab_pkg.bridge.inspect_prefab_overrides_native(
            instance_path=clean_path,
            scene_path=clean_scene,
            include_default_overrides=include_default_overrides,
            scope=scope,
            max_overrides=max_overrides,
        )
    except Exception as exc:
        logger.exception("inspect_prefab_overrides failed")
        return rejected(error=f"Bridge call failed: {exc}", **bridge_retry_fields(exc))

    if not isinstance(resp, dict):
        return rejected(error="Unity bridge returned a non-object payload for prefab override inspection.")

    return _build_result(
        instance_path=clean_path,
        scope=scope,
        include_default_overrides=include_default_overrides,
        resp=resp,
        limit=max_overrides,
    )
