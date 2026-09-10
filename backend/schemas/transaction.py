from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.base import BaseToolResult


class AnimationTransactionOperationModel(BaseModel):
    """Single operation within an atomic animation transaction."""

    model_config = ConfigDict(extra="ignore")

    operation_type: str = Field(
        ...,
        description="Type of operation: set_keyframe, move_keyframe, remove_keyframe, set_keyframe_hold, create_event, remove_event, ensure_continuity",
    )
    clip_path: str = Field(..., description="Project-relative path to the AnimationClip (.anim)")
    target_path: str = Field(default="", description="Relative hierarchy path to the target GameObject/bone")
    type_name: str = Field(default="Transform", description="Component type name (e.g. Transform)")
    property_name: str = Field(default="", description="Property name (e.g. m_LocalPosition, m_LocalRotation)")
    time: float = Field(default=0.0, description="Timestamp for keyframe or event")
    old_time: float = Field(default=0.0, description="Source timestamp for move_keyframe")
    new_time: float = Field(default=0.0, description="Destination timestamp for move_keyframe")
    start_time: float = Field(default=0.0, description="Start timestamp for hold operation")
    duration: float = Field(default=0.0, description="Duration in seconds for hold operation")
    value: float = Field(default=0.0, description="Single float value for keyframe/hold")
    values: list[float] | None = Field(default=None, description="Multi-channel float values for keyframe/hold")
    tangent_mode: str = Field(
        default="smooth",
        description="Tangent mode: smooth, linear, step, ease_in, ease_out, ease_in_out",
    )
    function_name: str = Field(default="", description="Animation event callback function name")
    int_parameter: int = Field(default=0, description="Integer parameter for animation event")
    float_parameter: float = Field(default=0.0, description="Float parameter for animation event")
    string_parameter: str = Field(default="", description="String parameter for animation event")


class AnimationTransactionResult(BaseToolResult):
    """Result of an atomic multi-operation animation transaction."""

    model_config = ConfigDict(extra="ignore")

    transaction_id: str = Field(default="", description="Unique identifier of the transaction")
    applied_operations_count: int = Field(default=0, description="Number of operations successfully executed")
    keyframes_modified_count: int = Field(default=0, description="Total keyframe channels written or altered")
    rollback_performed: bool = Field(
        default=False, description="True if any operation failed and all changes were rolled back"
    )
    backup_ids: list[str] = Field(
        default_factory=list, description="Pre-mutation backup IDs created before modifications"
    )
    affected_clips: list[str] = Field(default_factory=list, description="Distinct animation clip paths touched")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings encountered during execution")
