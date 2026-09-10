"""Typed result models for read-only Prefab asset and Prefab instance override inspection."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.base import BaseToolResult

PrefabKind = Literal["regular", "variant", "model", "unknown"]
"""Unity's PrefabAssetType for the inspected asset, narrowed to the kinds an agent can act on."""

PrefabConnectionStatus = Literal["connected", "missing_asset", "disconnected", "not_an_instance", "unknown"]
"""Whether a Prefab instance inside the inspected asset still resolves to its source Prefab."""


class PrefabComponentInfo(BaseModel):
    """One Component attached to a GameObject inside a Prefab asset."""

    type_name: str = Field(..., description="Component type name, e.g. 'Transform', 'MeshRenderer'")
    is_missing_script: bool = Field(
        default=False,
        description="True when Unity could not resolve the MonoBehaviour script backing this component",
    )


class PrefabObjectNode(BaseModel):
    """One GameObject in the Prefab asset hierarchy, addressed by a stable prefab-relative path."""

    relative_path: str = Field(
        ...,
        description="Path relative to the prefab root ('' for the root itself, 'Arm/Hand' below it), "
        "matching Unity's AnimationClip binding path convention",
    )
    name: str = Field(..., description="GameObject name")
    depth: int = Field(default=0, description="Depth below the prefab root (0 for the root)")
    active_self: bool = Field(default=True, description="GameObject.activeSelf as stored in the asset")
    components: list[PrefabComponentInfo] = Field(
        default_factory=list, description="Components on this GameObject, in serialized order"
    )
    is_nested_prefab_instance_root: bool = Field(
        default=False, description="True when this GameObject is the root of a nested Prefab instance"
    )
    nested_source_asset_path: str | None = Field(
        default=None, description="Project-relative path of the nested Prefab asset when this node is its instance root"
    )


class PrefabNestedInstance(BaseModel):
    """A nested Prefab instance found inside the inspected Prefab asset."""

    relative_path: str = Field(..., description="Path of the nested instance root relative to the prefab root")
    name: str = Field(..., description="Nested instance root GameObject name")
    source_asset_path: str | None = Field(
        default=None, description="Project-relative path of the source Prefab asset, None when it is missing"
    )
    source_guid: str | None = Field(default=None, description="GUID of the source Prefab asset when it resolves")
    connection_status: PrefabConnectionStatus = Field(
        default="unknown", description="Whether this nested instance still resolves to its source Prefab asset"
    )


class InspectPrefabAssetResult(BaseToolResult):
    """Result schema for read-only inspection of a Prefab asset without instantiating it in a scene."""

    asset_path: str = Field(..., description="Normalized project-relative path of the inspected asset")
    prefab_name: str = Field(default="", description="Prefab asset name (file name without extension)")
    guid: str = Field(default="", description="AssetDatabase GUID of the Prefab asset")
    prefab_kind: PrefabKind = Field(default="unknown", description="Prefab asset kind: regular, variant, or model")
    base_prefab_path: str | None = Field(
        default=None, description="For a Prefab Variant, the project-relative path of the base Prefab asset"
    )
    root_object_name: str = Field(default="", description="Name of the Prefab asset's root GameObject")
    root_connection_status: PrefabConnectionStatus = Field(
        default="not_an_instance",
        description="For a Variant, whether its base Prefab still resolves; 'not_an_instance' otherwise",
    )
    hierarchy: list[PrefabObjectNode] = Field(
        default_factory=list, description="Depth-first hierarchy of GameObjects, possibly truncated"
    )
    nested_prefabs: list[PrefabNestedInstance] = Field(
        default_factory=list, description="Nested Prefab instances inside this asset, in hierarchy order"
    )
    edit_target_asset_paths: list[str] = Field(
        default_factory=list,
        description="Unique, sorted Prefab asset paths a future edit could target: this asset, its base, "
        "and every resolvable nested source",
    )
    total_object_count: int = Field(default=0, description="Total GameObjects in the asset, before truncation")
    total_component_count: int = Field(default=0, description="Total Components in the asset, before truncation")
    truncated: bool = Field(default=False, description="True when the hierarchy was capped by the node limit")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking inspection warnings")


PrefabOverrideScope = Literal["nearest", "outermost"]
"""Which Prefab instance root an override inspection is anchored to."""

PrefabOverrideCategory = Literal[
    "modified_property",
    "added_component",
    "removed_component",
    "added_game_object",
    "removed_game_object",
]
"""The five kinds of change Unity records on a Prefab instance."""

PrefabValueKind = Literal["integer", "float", "boolean", "string", "enum", "array_size", "object_reference", "other"]
"""How a serialized property value is represented; 'other' carries Unity's raw modification text."""


class PrefabObjectReference(BaseModel):
    """Structured identity of an object referenced by a serialized property."""

    is_null: bool = Field(default=False, description="True when the reference is empty (None)")
    type_name: str | None = Field(default=None, description="Referenced object type, e.g. 'Material', 'Transform'")
    name: str | None = Field(default=None, description="Referenced object name")
    asset_path: str | None = Field(default=None, description="Project-relative asset path when the object is an asset")
    guid: str | None = Field(default=None, description="AssetDatabase GUID of the asset that contains the object")
    local_file_id: int | None = Field(default=None, description="Local file ID of the object inside its asset")
    scene_path: str | None = Field(default=None, description="Scene path (or unsaved scene name) for a scene object")
    hierarchy_path: str | None = Field(
        default=None,
        description="Rooted hierarchy path for a scene object, or asset-root-relative path for an object inside a Prefab",
    )


class PrefabPropertyValue(BaseModel):
    """One side of a property override: the source-asset value or the instance value."""

    kind: PrefabValueKind = Field(..., description="Value representation")
    value: bool | int | float | str | None = Field(
        default=None, description="Scalar value; None for object references (see object_reference)"
    )
    object_reference: PrefabObjectReference | None = Field(
        default=None, description="Structured identity when kind is 'object_reference'"
    )


class PrefabOverride(BaseModel):
    """One typed change between a Prefab instance and its source Prefab asset."""

    override_id: str = Field(
        ...,
        description="Stable ID ('ovr_' + 16 hex chars) hashed from the override's semantic identity; "
        "identical scene state yields identical IDs",
    )
    category: PrefabOverrideCategory = Field(..., description="Kind of change")
    object_path: str | None = Field(
        default=None,
        description="Instance-relative path of the affected GameObject ('' is the instance root); for removed "
        "components/GameObjects, the instance GameObject the removal happened on/under",
    )
    source_object_path: str | None = Field(
        default=None,
        description="Path of the corresponding GameObject inside the source Prefab asset; None for added GameObjects",
    )
    component_type: str | None = Field(default=None, description="Component type name for component-level changes")
    component_ordinal: int | None = Field(
        default=None,
        description="0-based position among components of the same type, only when the GameObject has several",
    )
    property_path: str | None = Field(default=None, description="Serialized property path for modified properties")
    source_value: PrefabPropertyValue | None = Field(
        default=None, description="Value in the source Prefab; None when the property does not exist there"
    )
    instance_value: PrefabPropertyValue | None = Field(default=None, description="Value on the scene instance")
    is_default_override: bool = Field(
        default=False,
        description="True for Unity default overrides (root placement/name) that Unity never applies to an asset",
    )
    target_asset_paths: list[str] = Field(
        default_factory=list,
        description="Editable Prefab assets this override could be applied to, from the instance's immediate "
        "source inwards; empty when not applicable",
    )
    recommended_target_asset_path: str | None = Field(
        default=None, description="Suggested target: the inspected scope's source asset when it can accept the change"
    )
    applicable: bool = Field(default=False, description="True when at least one target asset can accept this override")
    not_applicable_reason: str | None = Field(default=None, description="Why the override cannot be applied")
    id_collision: bool = Field(
        default=False, description="True when another override in this result shares the ID; never safely addressable"
    )
    description: str = Field(default="", description="Short human-readable summary of the change")


class PrefabOverrideCounts(BaseModel):
    """Override totals per category, after default-override filtering and before truncation."""

    modified_property: int = 0
    added_component: int = 0
    removed_component: int = 0
    added_game_object: int = 0
    removed_game_object: int = 0

    def total(self) -> int:
        return (
            self.modified_property
            + self.added_component
            + self.removed_component
            + self.added_game_object
            + self.removed_game_object
        )


class PrefabPathCandidate(BaseModel):
    """One GameObject an ambiguous hierarchy path matched, in its canonical indexed form."""

    scene_path: str | None = Field(default=None, description="Scene path (or unsaved scene name)")
    hierarchy_path: str = Field(..., description="Unambiguous rooted path, e.g. 'Level/Crate[1]/Lid'")


class InspectPrefabOverridesResult(BaseToolResult):
    """Result schema for the read-only diff between a scene Prefab instance and its source asset."""

    instance_path: str = Field(..., description="Normalized hierarchy path that was requested")
    scene_path: str | None = Field(default=None, description="Scene containing the instance")
    instance_root_path: str | None = Field(
        default=None, description="Rooted path of the Prefab instance root selected by the scope"
    )
    outermost_instance_root_path: str | None = Field(
        default=None, description="Rooted path of the outermost Prefab instance root containing the object"
    )
    scope: PrefabOverrideScope = Field(default="nearest", description="Instance root the diff is anchored to")
    source_asset_path: str | None = Field(default=None, description="Source Prefab asset of the selected instance root")
    source_guid: str | None = Field(default=None, description="GUID of the source Prefab asset")
    prefab_kind: PrefabKind = Field(default="unknown", description="Source asset kind: regular, variant, or model")
    connection_status: PrefabConnectionStatus = Field(
        default="unknown", description="Whether the instance still resolves to its source Prefab asset"
    )
    include_default_overrides: bool = Field(default=False, description="Whether default overrides were requested")
    total_override_count: int = Field(default=0, description="Overrides matching the filter, before truncation")
    override_counts: PrefabOverrideCounts = Field(
        default_factory=PrefabOverrideCounts, description="Per-category totals, before truncation"
    )
    excluded_default_override_count: int = Field(
        default=0, description="Default overrides left out because include_default_overrides was false"
    )
    truncated: bool = Field(default=False, description="True when the override list was capped by max_overrides")
    overrides: list[PrefabOverride] = Field(default_factory=list, description="Deterministically ordered overrides")
    path_candidates: list[PrefabPathCandidate] = Field(
        default_factory=list, description="Matches of an ambiguous instance_path, to retry with"
    )
    warnings: list[str] = Field(default_factory=list, description="Non-blocking inspection warnings")
