from __future__ import annotations

from typing import Literal

from backend.app import mcp
from backend.bridge.client import UnityBridge
from backend.schemas.camera_action import CameraSubjectContactResult


@mcp.tool()
async def solve_camera_subject_contact(  # noqa: PLR0913
    character_path: str,
    character_clip_path: str,
    camera_name: str,
    camera_clip_path: str | None = None,
    effector: Literal["left_foot", "right_foot", "left_hand", "right_hand"] = "right_foot",
    impact_time: float = 0.5,
    contact_duration: float = 0.2,
    lens_viewport: list[float] | None = None,
    lens_distance_meters: float = 0.3,
    hit_stop_duration: float = 0.08,
    camera_recoil_impulse: list[float] | None = None,
) -> CameraSubjectContactResult:
    """
    Solves composite cinematic and combat contact between character limbs and the camera.

    Coordinates camera recoil, character Two-Bone IK lens alignment, and hit-stop keyframe
    holds into a single unified operation:
    1. Projects character foot/hand to exact camera lens viewport at impact timestamp.
    2. Bakes effector contact with cubic Hermite lead-in and lead-out transitions.
    3. Injects camera position recoil curve with exponential damping.
    4. Applies synchronized hit-stop hold to both character and camera curves.

    Creates pre-mutation backups of character and camera clips before editing.

    Args:
        character_path: Scene path to character GameObject.
        character_clip_path: Project-relative path to character AnimationClip.
        camera_name: Name of the active camera in scene.
        camera_clip_path: Optional project-relative path to camera AnimationClip for recoil authoring.
        effector: Character limb to align ('left_foot', 'right_foot', 'left_hand', 'right_hand').
        impact_time: Authoritative impact timestamp (seconds) in animation.
        contact_duration: Duration of impact hold (seconds).
        lens_viewport: Target normalized [u, v] in camera viewport (default [0.5, 0.5]).
        lens_distance_meters: Distance from camera lens in meters (default 0.3m).
        hit_stop_duration: Duration of frozen hit-stop hold (seconds, default 0.08s).
        camera_recoil_impulse: Local directional impulse [x, y, z] applied to camera (default [0, -0.15, -0.4]).

    Returns:
        A CameraSubjectContactResult recording backup IDs, impact coordinates, and screen residuals.
    """
    async with UnityBridge() as bridge:
        resp = await bridge.solve_camera_subject_contact_native(
            character_path=character_path,
            character_clip_path=character_clip_path,
            camera_name=camera_name,
            camera_clip_path=camera_clip_path,
            effector=effector,
            impact_time=impact_time,
            contact_duration=contact_duration,
            lens_viewport=lens_viewport,
            lens_distance_meters=lens_distance_meters,
            hit_stop_duration=hit_stop_duration,
            camera_recoil_impulse=camera_recoil_impulse,
        )

    return CameraSubjectContactResult(
        success=bool(resp.get("success", False)),
        error=resp.get("error"),
        character_backup_id=resp.get("characterBackupId"),
        camera_backup_id=resp.get("cameraBackupId"),
        impact_world_position=list(resp.get("impactWorldPosition", [])),
        impact_screen_residual_pixels=list(resp.get("impactScreenResidualPixels", [])),
        max_limb_reach_ratio=float(resp.get("maxLimbReachRatio", 0.0)),
        keyframes_modified_count=int(resp.get("keyframesModifiedCount", 0)),
        warnings=list(resp.get("warnings", [])),
    )
