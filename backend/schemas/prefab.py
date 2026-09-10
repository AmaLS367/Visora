"""Typed result models for read-only Prefab asset inspection."""

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
