from pydantic import BaseModel, Field

from backend.schemas.base import BaseToolResult


class GazeJointRotation(BaseModel):
    """Rotation applied to an individual joint in the gaze/look-at hierarchy."""

    bone_name: str = Field(
        ...,
        description="Name of the affected transform/bone (e.g. Chest, Neck, Head)",
    )
    local_euler: list[float] = Field(
        ...,
        description="Local Euler angles [pitch, yaw, roll] in degrees",
    )
    local_quaternion: list[float] = Field(
        ...,
        description="Local Quaternion [x, y, z, w]",
    )
    allocated_yaw_deg: float = Field(
        ...,
        description="Yaw angle (horizontal turn) allocated to this joint",
    )
    allocated_pitch_deg: float = Field(
        ...,
        description="Pitch angle (vertical tilt) allocated to this joint",
    )
    was_clamped: bool = Field(
        ...,
        description="True if the allocated angle hit the anatomical clamp limit",
    )


class CharacterGazeResult(BaseToolResult):
    """Result of solving multi-joint character gaze and head/body orientation."""

    target_object_path: str = Field(
        ...,
        description="Hierarchy path to the character GameObject",
    )
    target_look_at_position: list[float] = Field(
        default_factory=list,
        description="Resolved world-space position [x, y, z] the character is looking at",
    )
    total_target_angle_deg: float = Field(
        default=0.0,
        description="Total angular difference (degrees) between character forward and target",
    )
    is_target_behind_character: bool = Field(
        default=False,
        description="True if target direction is behind character body (> 90°)",
    )
    was_clamped: bool = Field(
        default=False,
        description="True if one or more joints were clamped by anatomical limits",
    )
    residual_gaze_error_deg: float = Field(
        default=0.0,
        description="Angular error (degrees) between head forward and target direction after solving",
    )
    solved_joints: list[GazeJointRotation] = Field(
        default_factory=list,
        description="Hierarchical rotation outputs for each adjusted bone",
    )
    backup_id: str | None = Field(
        default=None,
        description="Pre-mutation backup identifier if changes were baked to an AnimationClip",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings or diagnostic messages",
    )
