from pydantic import Field

from backend.schemas.base import BaseToolResult


class TwoBoneIKSolveResult(BaseToolResult):
    """Result of solving analytic Two-Bone Inverse Kinematics on a character limb chain."""

    target_object_path: str = Field(
        ...,
        description="Hierarchy path to the target character GameObject",
    )
    effector: str | None = Field(
        default=None,
        description="Humanoid effector name ('left_foot', 'right_foot', 'left_hand', 'right_hand')",
    )
    root_bone: str | None = Field(
        default=None,
        description="Resolved root bone name/path (e.g. UpperLeg / UpperArm)",
    )
    mid_bone: str | None = Field(
        default=None,
        description="Resolved mid bone name/path (e.g. LowerLeg / LowerArm)",
    )
    end_bone: str | None = Field(
        default=None,
        description="Resolved end bone name/path (e.g. Foot / Hand)",
    )
    root_rotation_euler: list[float] | None = Field(
        default=None,
        description="Solved local Euler rotation [x, y, z] for the root bone",
    )
    root_rotation_quaternion: list[float] | None = Field(
        default=None,
        description="Solved local Quaternion rotation [x, y, z, w] for the root bone",
    )
    mid_rotation_euler: list[float] | None = Field(
        default=None,
        description="Solved local Euler rotation [x, y, z] for the mid bone",
    )
    mid_rotation_quaternion: list[float] | None = Field(
        default=None,
        description="Solved local Quaternion rotation [x, y, z, w] for the mid bone",
    )
    end_rotation_euler: list[float] | None = Field(
        default=None,
        description="Solved local Euler rotation [x, y, z] for the end bone",
    )
    end_rotation_quaternion: list[float] | None = Field(
        default=None,
        description="Solved local Quaternion rotation [x, y, z, w] for the end bone",
    )
    target_clamped: bool = Field(
        default=False,
        description="True if target was beyond limb reach or within soft damping threshold",
    )
    reach_distance: float = Field(
        default=0.0,
        description="Maximum reach of the 2-bone chain (l1 + l2)",
    )
    actual_distance: float = Field(
        default=0.0,
        description="Distance from root bone to the requested target position",
    )
    position_residual: float = Field(
        default=0.0,
        description="Distance between solved end effector position and requested target position",
    )
    rotation_residual_deg: float = Field(
        default=0.0,
        description="Angular error (degrees) between solved end rotation and requested target rotation",
    )
    backup_id: str | None = Field(
        default=None,
        description="Pre-mutation backup snapshot identifier if baked to AnimationClip",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings or diagnostic messages",
    )


class ViewportEffectorPlacementResult(BaseToolResult):
    """Result of placing an effector at a normalized 2D camera viewport position and depth."""

    camera_name: str = Field(
        default="Main Camera",
        description="Name of the camera used to compute viewport projection",
    )
    target_object_path: str = Field(
        ...,
        description="Hierarchy path to the target character GameObject",
    )
    effector: str | None = Field(
        default=None,
        description="Effector name ('left_foot', 'right_foot', 'left_hand', 'right_hand')",
    )
    target_world_position: list[float] = Field(
        default_factory=list,
        description="Unprojected 3D world target position [x, y, z] derived from camera viewport ray",
    )
    solved_world_position: list[float] = Field(
        default_factory=list,
        description="Actual 3D world position [x, y, z] of the end effector after IK solve",
    )
    actual_viewport: list[float] = Field(
        default_factory=list,
        description="Reprojected camera viewport coordinate [u, v, depth]",
    )
    screen_residual_pixels: list[float] = Field(
        default_factory=list,
        description="Sub-pixel error [dx, dy] on the camera sensor resolution",
    )
    depth_residual_meters: float = Field(
        default=0.0,
        description="Difference (meters) between requested camera depth and actual distance",
    )
    is_in_frustum: bool = Field(
        default=True,
        description="True if the solved effector is inside camera viewport bounds [0..1, 0..1]",
    )
    is_clipped_by_near_plane: bool = Field(
        default=False,
        description="True if the solved effector penetrates the camera near clipping plane",
    )
    reach_distance: float = Field(
        default=0.0,
        description="Maximum reach of the limb chain",
    )
    actual_distance: float = Field(
        default=0.0,
        description="Distance from root bone to the unprojected world target",
    )
    target_clamped: bool = Field(
        default=False,
        description="True if target was clamped by reach or soft-knee limit",
    )
    ik_result: TwoBoneIKSolveResult | None = Field(
        default=None,
        description="Detailed underlying Two-Bone IK solve result",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings or diagnostic messages",
    )
