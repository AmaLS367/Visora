from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.base import BaseToolResult


class AnimationBindingCurve(BaseModel):
    """Details about a specific property curve binding in an AnimationClip."""

    path: str = Field(description="Hierarchy path to the animated GameObject/bone")
    property_name: str = Field(description="Property being animated (e.g., m_LocalPosition.x, m_LocalRotation.x)")
    type_name: str = Field(default="UnityEngine.Transform", description="Type name of the animated component/class")
    curve_type: str = Field(
        default="unknown",
        description="Categorized curve type (position, rotation, scale, float_property, reference)",
    )
    keyframe_count: int = Field(default=0, description="Total number of keyframes in the curve")
    min_value: float | None = Field(default=None, description="Minimum evaluated value in keyframes")
    max_value: float | None = Field(default=None, description="Maximum evaluated value in keyframes")
    start_value: float | None = Field(default=None, description="Value at the first keyframe (time 0 or earliest)")
    end_value: float | None = Field(default=None, description="Value at the last keyframe")
    is_constant: bool = Field(
        default=False,
        description="True if all keyframes share identical or near-identical values",
    )


class AnimationEventInfo(BaseModel):
    """Metadata for an animation event attached to the AnimationClip."""

    time: float = Field(description="Time in seconds where the event is triggered")
    function_name: str = Field(description="Target C# function name invoked by the event")
    string_param: str = Field(default="", description="String parameter passed to the callback")
    float_param: float = Field(default=0.0, description="Float parameter passed to the callback")
    int_param: int = Field(default=0, description="Int parameter passed to the callback")


class DangerousCurveWarning(BaseModel):
    """Warning and risk classification for anomalous or potentially destructive animation curves."""

    risk_level: str = Field(
        description="Risk level of the curve: 'critical', 'warning', or 'info'",
    )
    binding_path: str = Field(description="Hierarchy path of the animated target")
    property_name: str = Field(description="Animated property name")
    reason: str = Field(description="Short reason for the warning")
    description: str = Field(description="Detailed explanation of the risk or anomaly")
    recommendation: str = Field(description="Suggested agent/developer action to resolve the risk")


class TransformPose(BaseModel):
    """Snapshot of a transform's state in local and world space."""

    path: str = Field(description="Hierarchy path to this transform")
    name: str = Field(default="", description="Transform GameObject name")
    local_position: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        description="Local position [x, y, z]",
    )
    local_rotation_euler: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        description="Local rotation in Euler angles [x, y, z]",
    )
    local_scale: list[float] = Field(
        default_factory=lambda: [1.0, 1.0, 1.0],
        description="Local scale [x, y, z]",
    )
    world_position: list[float] | None = Field(
        default=None,
        description="World position [x, y, z] if queried",
    )
    world_rotation_euler: list[float] | None = Field(
        default=None,
        description="World Euler angles [x, y, z] if queried",
    )
    world_scale: list[float] | None = Field(
        default=None,
        description="World lossy scale [x, y, z] if queried",
    )


class ClipInspectorResult(BaseToolResult):
    """Result schema for the animation clip inspector tool."""

    clip_name: str | None = Field(default=None, description="Name of the inspected animation clip")
    clip_path: str | None = Field(default=None, description="Project asset path to the animation clip")
    length: float | None = Field(default=None, description="Length of the animation clip in seconds")
    fps: float | None = Field(default=None, description="Frame rate of the animation clip")
    loop_time: bool | None = Field(default=None, description="Whether loopTime is enabled on the clip")
    wrap_mode: str | None = Field(
        default=None, description="WrapMode of the clip (e.g., Default, Once, Loop, PingPong)"
    )
    is_legacy: bool | None = Field(default=None, description="Whether this clip is configured as a legacy animation")
    has_root_motion: bool = Field(
        default=False, description="Whether the clip contains root motion displacement curves"
    )
    curves_count: int | None = Field(default=None, description="Total number of animation curves in this clip")
    events_count: int = Field(default=0, description="Total number of animation events in this clip")
    bindings: list[AnimationBindingCurve] = Field(
        default_factory=list,
        description="List of all curve bindings in the clip",
    )
    dangerous_curves: list[DangerousCurveWarning] = Field(
        default_factory=list,
        description="Identified problematic or dangerous curves requiring attention",
    )
    events: list[AnimationEventInfo] = Field(
        default_factory=list,
        description="List of animation events defined on the clip",
    )
    summary_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics (e.g. position_curves_count, scale_curves_count, constant_curves_count)",
    )


class SampleAnimationResult(BaseToolResult):
    """Result schema for the animation sampling tool."""

    clip_name: str | None = Field(default=None, description="Name of the sampled animation clip")
    clip_path: str | None = Field(default=None, description="Asset path to the sampled clip")
    target_game_object: str | None = Field(
        default=None,
        description="Scene hierarchy path to the sampled target GameObject",
    )
    sample_time: float | None = Field(default=None, description="Time in seconds at which the clip was sampled")
    normalized_time: float | None = Field(
        default=None,
        description="Normalized time (0.0 to 1.0) of the sample point",
    )
    pose_restored: bool = Field(
        default=True,
        description="Whether the original GameObject pose was restored after sampling",
    )
    sampled_transforms: dict[str, TransformPose] = Field(
        default_factory=dict,
        description="Dictionary mapping bone/transform paths to their sampled TransformPose",
    )
    root_motion_delta: list[float] | None = Field(
        default=None,
        description="Estimated root position displacement [dx, dy, dz] relative to rest pose if available",
    )
    anomalies_detected: list[str] = Field(
        default_factory=list,
        description="List of detected anomalies in the sampled pose (e.g., negative scale, extreme position)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Informational warnings regarding sampling context or missing bones",
    )


class BoneNode(BaseModel):
    """A single transform node within a walked skeleton hierarchy."""

    path: str = Field(description="Hierarchy path relative to the skeleton root ('' for the root itself)")
    name: str = Field(description="GameObject name of this bone")
    parent_path: str | None = Field(default=None, description="Relative path of the parent bone, None for the root")
    depth: int = Field(default=0, description="Depth of this bone relative to the root (root is 0)")
    child_count: int = Field(default=0, description="Number of direct child transforms")
    local_position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0], description="Local position [x, y, z]")
    local_rotation_euler: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0], description="Local rotation in Euler angles [x, y, z]"
    )
    local_scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0], description="Local scale [x, y, z]")


class DuplicateBoneGroup(BaseModel):
    """A set of bones sharing the exact same name within one hierarchy."""

    name: str = Field(description="The bone name shared by every path in this group")
    paths: list[str] = Field(description="All hierarchy paths carrying this duplicated name")


class HelperBoneWarning(BaseModel):
    """A bone flagged as a likely helper/dummy/twist bone by naming convention."""

    path: str = Field(description="Hierarchy path of the flagged bone")
    name: str = Field(description="Name of the flagged bone")
    reason: str = Field(description="Which helper-naming pattern matched and why")


class MmdBoneChain(BaseModel):
    """A paired primary/physics bone chain following the MMD '_D' dynamics-bone convention."""

    base_name: str = Field(description="Shared base bone name (without the physics-bone suffix)")
    primary_path: str = Field(description="Hierarchy path of the animation-driven primary bone")
    d_bone_path: str = Field(description="Hierarchy path of the physics-driven dynamics ('_D') bone")


class BoneMatch(BaseModel):
    """A single bone name search result."""

    path: str = Field(description="Hierarchy path of the matched bone")
    name: str = Field(description="Name of the matched bone")
    match_type: str = Field(description="'exact' or 'fuzzy'")
    score: float = Field(description="Match confidence: 1.0 for exact matches, similarity ratio (0-1) for fuzzy")


class SkeletonMapperResult(BaseToolResult):
    """Result schema for the skeleton mapper tool."""

    root_transform_path: str | None = Field(default=None, description="Hierarchy path to the inspected root")
    bone_count: int = Field(default=0, description="Total number of bones/transforms found under the root")
    bones: list[BoneNode] = Field(default_factory=list, description="Every bone found under the root")
    mapping_source: str = Field(
        default="none",
        description="How the humanoid mapping was derived: 'avatar' (authoritative), 'heuristic' (fuzzy), or 'none'",
    )
    is_valid: bool = Field(default=False, description="True if the skeleton mapping is valid/complete")
    mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Dictionary mapping standard humanoid bone names to their transform paths",
    )
    missing_bones: list[str] = Field(
        default_factory=list,
        description="List of required bones that are missing from the mapping",
    )
    duplicate_bones: list[DuplicateBoneGroup] = Field(
        default_factory=list,
        description="Groups of bones sharing the exact same name",
    )
    helper_bones: list[HelperBoneWarning] = Field(
        default_factory=list,
        description="Bones flagged as likely helper/dummy/twist bones by naming convention",
    )
    mmd_bone_chains: list[MmdBoneChain] = Field(
        default_factory=list,
        description="Detected MMD-style primary/physics ('_D') bone chain pairs",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="General warnings about the skeleton inspection (e.g. no humanoid avatar found)",
    )


class BoneSearchResult(BaseToolResult):
    """Result schema for the bone search tool."""

    root_transform_path: str | None = Field(default=None, description="Hierarchy path to the searched root")
    query: str | None = Field(default=None, description="The bone name query that was searched for")
    matches: list[BoneMatch] = Field(default_factory=list, description="Matching bones, best matches first")
