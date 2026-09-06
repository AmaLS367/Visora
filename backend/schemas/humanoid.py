from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.animation import AnimationPreviewResult
from backend.schemas.base import BaseToolResult


class AvatarBlocker(BaseModel):
    """Specific blocker or issue detected in a skeleton/avatar hierarchy."""

    bone_name: str | None = Field(
        default=None,
        description="Name of the affected bone, or None if general issue",
    )
    category: Literal["missing_bone", "hierarchy", "posture", "duplicate_name", "scale"] = Field(
        ...,
        description="Category of the detected issue",
    )
    severity: Literal["blocker", "warning"] = Field(
        ...,
        description="'blocker' prevents Humanoid Avatar creation; 'warning' degrades motion quality",
    )
    message: str = Field(
        ...,
        description="Detailed diagnostic description of the issue",
    )
    suggested_fix: str = Field(
        ...,
        description="Concrete suggestion or action to resolve this issue",
    )


class TPoseAssessment(BaseModel):
    """Assessment of whether a skeleton conforms to the standard Humanoid T-pose."""

    arms_horizontal_angle: float = Field(
        ...,
        description="Average angle of upper arms relative to horizontal (degrees). ~90° in T-pose, ~45° in A-pose",
    )
    legs_vertical_angle: float = Field(
        ...,
        description="Average angle of upper legs relative to vertical (degrees)",
    )
    is_tpose: bool = Field(
        ...,
        description="True if posture is within acceptable T-pose tolerance",
    )
    is_apose: bool = Field(
        ...,
        description="True if posture is detected as an A-pose requiring normalization",
    )
    symmetry_score: float = Field(
        ...,
        description="Symmetry score between left and right limbs (0.0 to 1.0, 1.0 being perfectly symmetric)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Specific posture warnings (e.g. tilted head, bent knees)",
    )


class HumanoidValidationResult(BaseToolResult):
    """Result schema for validate_humanoid_avatar."""

    target_path: str | None = Field(
        default=None,
        description="Hierarchy path of the inspected in-scene GameObject",
    )
    asset_path: str | None = Field(
        default=None,
        description="Project asset path of the inspected 3D model",
    )
    is_valid_humanoid: bool = Field(
        default=False,
        description="True if the model/rig meets all requirements for a valid Humanoid Avatar",
    )
    avatar_status: str = Field(
        default="unknown",
        description="Status: 'valid_humanoid', 'generic_avatar', 'missing_avatar', 'invalid_avatar', 'not_configured'",
    )
    blockers: list[AvatarBlocker] = Field(
        default_factory=list,
        description="List of detected blockers and warnings",
    )
    missing_required_bones: list[str] = Field(
        default_factory=list,
        description="Required Humanoid bones that could not be mapped (from Unity's 15 required bones)",
    )
    missing_optional_bones: list[str] = Field(
        default_factory=list,
        description="Optional Humanoid bones missing (Chest, Neck, Toes, Shoulders)",
    )
    posture: TPoseAssessment | None = Field(
        default=None,
        description="Evaluation of bind-pose T-pose conformity",
    )
    bone_mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of standard Humanoid bone names to skeleton transform paths",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="General inspection warnings",
    )


class HumanoidConfigurationResult(BaseToolResult):
    """Result schema for configure_humanoid_avatar."""

    asset_path: str | None = Field(
        default=None,
        description="Asset path of the reconfigured 3D model",
    )
    animation_type: str = Field(
        default="Human",
        description="ModelImporter animation type configured",
    )
    avatar_created: bool = Field(
        default=False,
        description="True if an Avatar was generated or assigned",
    )
    avatar_valid: bool = Field(
        default=False,
        description="True if the resulting Avatar is valid and recognized as Humanoid by Unity",
    )
    configured_bones_count: int = Field(
        default=0,
        description="Number of human bones configured in the avatar description",
    )
    blockers: list[AvatarBlocker] = Field(
        default_factory=list,
        description="Blockers encountered during avatar creation",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings reported during reimport or configuration",
    )


class EffectorContactPhase(BaseModel):
    """A continuous time interval where an effector is in contact with the surface."""

    effector: str = Field(
        ...,
        description="Effector name, e.g. 'left_foot', 'right_foot', 'left_hand', 'right_hand'",
    )
    start_time: float = Field(
        ...,
        description="Timestamp in seconds when contact begins",
    )
    end_time: float = Field(
        ...,
        description="Timestamp in seconds when contact ends",
    )
    duration: float = Field(
        ...,
        description="Duration of contact in seconds",
    )
    average_position: list[float] = Field(
        ...,
        description="Average world position [X, Y, Z] during contact",
    )
    is_sliding: bool = Field(
        ...,
        description="True if horizontal drift exceeds threshold during contact",
    )
    slide_distance: float = Field(
        default=0.0,
        description="Total horizontal drift distance in meters during contact",
    )


class ContactAnomaly(BaseModel):
    """An anomaly detected in effector contact dynamics."""

    effector: str = Field(
        ...,
        description="Effector name",
    )
    anomaly_type: Literal["foot_sliding", "ground_penetration", "floating", "hyperextension"] = Field(
        ...,
        description="Type of contact anomaly",
    )
    start_time: float = Field(
        ...,
        description="Start time of the anomaly in seconds",
    )
    end_time: float = Field(
        ...,
        description="End time of the anomaly in seconds",
    )
    severity: Literal["critical", "warning"] = Field(
        ...,
        description="Severity level of the anomaly",
    )
    value: float = Field(
        ...,
        description="Numerical metric (e.g. slide distance in meters, penetration depth in meters)",
    )
    description: str = Field(
        ...,
        description="Human-readable description of the anomaly",
    )


class ContactEffectorDiagnostic(BaseModel):
    """Diagnostics for a single limb effector's IK chain support."""

    effector: str = Field(..., description="Effector name")
    is_supported: bool = Field(..., description="True if the skeleton has a valid Two-Bone IK chain")
    root_bone: str | None = Field(default=None, description="Upper bone (e.g. Thigh / UpperArm)")
    mid_bone: str | None = Field(default=None, description="Middle bone (e.g. Calf / Forearm)")
    end_bone: str | None = Field(default=None, description="End bone (e.g. Foot / Hand)")
    limb_length: float = Field(default=0.0, description="Total limb length (L1 + L2) in meters")
    blocker_reason: str | None = Field(default=None, description="Reason if limb chain is unsupported")


class ContactAnalysisResult(BaseToolResult):
    """Result schema for analyze_contact_constraints."""

    clip_path: str | None = Field(default=None, description="Asset path of the analyzed AnimationClip")
    target_object_path: str | None = Field(default=None, description="Scene path of the target character")
    supported_effectors: list[ContactEffectorDiagnostic] = Field(
        default_factory=list,
        description="Limb effectors verified and supported for IK",
    )
    unsupported_effectors: list[ContactEffectorDiagnostic] = Field(
        default_factory=list,
        description="Limb effectors lacking valid Two-Bone chains",
    )
    contact_phases: list[EffectorContactPhase] = Field(
        default_factory=list,
        description="Identified contact intervals per effector",
    )
    anomalies: list[ContactAnomaly] = Field(
        default_factory=list,
        description="Detected contact anomalies (sliding, penetration, floating, hyperextension)",
    )
    total_slide_distance: float = Field(
        default=0.0,
        description="Sum of all horizontal foot slide distances in meters",
    )
    max_ground_penetration: float = Field(
        default=0.0,
        description="Maximum depth below ground plane in meters",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="General analysis warnings",
    )


class BakeContactConstraintsResult(BaseToolResult):
    """Result schema for bake_contact_constraints."""

    source_clip_path: str | None = Field(default=None, description="Original clip path")
    output_clip_path: str | None = Field(default=None, description="Path to the baked clip (.anim asset)")
    backup_id: str | None = Field(
        default=None,
        description="ID of pre-mutation backup created in VisoraBackups/ if mutated in place",
    )
    effectors_baked: list[str] = Field(default_factory=list, description="Effectors whose curves were adjusted")
    keyframes_modified_count: int = Field(default=0, description="Number of curve keyframes updated or added")
    slide_reduction_percent: float = Field(
        default=0.0,
        description="Percentage reduction in foot sliding achieved by the bake",
    )
    warnings: list[str] = Field(default_factory=list, description="Warnings encountered during IK solving or baking")


class HumanoidRetargetPreviewResult(BaseToolResult):
    """Result schema for preview_humanoid_retarget."""

    target_object_path: str | None = Field(default=None, description="Target character in scene")
    clip_path: str | None = Field(default=None, description="AnimationClip sampled")
    is_compatible: bool = Field(default=False, description="True if target avatar and clip can retarget")
    source_avatar_type: str = Field(default="unknown", description="'humanoid' or 'generic'")
    target_avatar_type: str = Field(default="unknown", description="'humanoid' or 'generic'")
    height_ratio: float = Field(default=1.0, description="Target height / source height scale factor")
    detected_retarget_issues: list[str] = Field(
        default_factory=list,
        description="Specific issues found during retargeting (e.g. limb hyperextension, ground penetration)",
    )
    preview: AnimationPreviewResult | None = Field(
        default=None,
        description="Full preview result with video/frame capture and motion summary",
    )
    warnings: list[str] = Field(default_factory=list, description="Retargeting warnings")
