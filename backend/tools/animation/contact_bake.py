from typing import Literal

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas.contact_bake import BakeEffectorContactResult
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, logger, warns

_CAPABILITY = "effector_contact_baking"


@mcp.tool()
async def bake_effector_contact(  # noqa: PLR0913
    clip_path: str,
    target_object_path: str,
    effector: Literal["left_foot", "right_foot", "left_hand", "right_hand"],
    target_type: Literal["world_point", "scene_object", "camera_viewport"] = "world_point",
    target_position: list[float] | None = None,
    scene_object_path: str | None = None,
    camera_name: str | None = None,
    viewport_coordinates: list[float] | None = None,
    viewport_depth: float = 0.5,
    time_range: list[float] | None = None,
    blend_in_seconds: float = 0.1,
    blend_out_seconds: float = 0.1,
    pole_vector: list[float] | None = None,
    target_rotation: list[float] | None = None,
) -> BakeEffectorContactResult:
    """
    Bakes generalized 3D effector contacts into an AnimationClip with cubic Hermite ease curves.

    Locks any character limb (foot, hand) to a static 3D world position, a moving scene object,
    or a camera viewport position over a specified time interval [start, end].
    Smoothly blends into the contact using a lead-in transition and blends back to unconstrained
    motion via a lead-out transition. Keyframes outside the contact window are left intact.

    Enforces quaternion continuity (EnsureQuaternionContinuity) and snapshots pre-mutation backups
    in VisoraBackups/ before writing curves.

    Args:
        clip_path: Project-relative path to the AnimationClip (.anim).
        target_object_path: Scene path to the character GameObject.
        effector: Limb effector to solve ('left_foot', 'right_foot', 'left_hand', 'right_hand').
        target_type: Target category ('world_point', 'scene_object', 'camera_viewport').
        target_position: Static [x, y, z] coordinates when target_type is 'world_point'.
        scene_object_path: Scene GameObject path when target_type is 'scene_object'.
        camera_name: Camera name when target_type is 'camera_viewport'.
        viewport_coordinates: Normalized [u, v] coordinates in [0, 1] for camera viewport.
        viewport_depth: Distance from camera lens in meters (depth >= 0.05).
        time_range: [start_time, end_time] interval in seconds; omit to cover the whole clip.
        blend_in_seconds: Duration of lead-in cubic Hermite ease curve.
        blend_out_seconds: Duration of lead-out cubic Hermite ease curve.
        pole_vector: Optional [x, y, z] pole vector guiding knee/elbow bend plane.
        target_rotation: Optional [x, y, z, w] orientation for the end effector.

    Returns:
        A BakeEffectorContactResult recording modified keyframes count, backup ID, and residual error.
    """
    if viewport_depth < 0.05:
        return BakeEffectorContactResult(
            success=False, error="viewport_depth must be at least 0.05 meters.", clip_path=clip_path, effector=effector
        )
    if time_range is not None and len(time_range) != 2:
        return BakeEffectorContactResult(
            success=False,
            error="time_range must be [start_time, end_time].",
            clip_path=clip_path,
            effector=effector,
        )

    edit_mode_err = await _require_edit_mode()
    if edit_mode_err:
        return BakeEffectorContactResult(success=False, error=edit_mode_err, clip_path=clip_path, effector=effector)

    if not await _bridge_supports(_CAPABILITY):
        return BakeEffectorContactResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY}'. Update Visora Unity package.",
            clip_path=clip_path,
            effector=effector,
        )

    try:
        resp = await animation_pkg.bridge.bake_effector_contact_native(
            clip_path=clip_path,
            target_object_path=target_object_path,
            effector=effector,
            target_type=target_type,
            target_position=target_position,
            scene_object_path=scene_object_path,
            camera_name=camera_name,
            viewport_coordinates=viewport_coordinates,
            viewport_depth=viewport_depth,
            time_range=time_range,
            blend_in_seconds=blend_in_seconds,
            blend_out_seconds=blend_out_seconds,
            pole_vector=pole_vector,
            target_rotation=target_rotation,
        )
    except Exception as exc:
        logger.exception("Error executing bake_effector_contact")
        return BakeEffectorContactResult(
            success=False, error=f"Bridge call failed: {exc}", clip_path=clip_path, effector=effector
        )

    return BakeEffectorContactResult(
        success=bool(resp.get("success", False)),
        error=resp.get("error"),
        clip_path=str(resp.get("clipPath", clip_path)),
        effector=str(resp.get("effector", effector)),
        backup_id=resp.get("backupId"),
        keyframes_modified_count=int(resp.get("keyframesModifiedCount", 0)),
        max_effector_displacement=float(resp.get("maxEffectorDisplacement", 0.0)),
        residual_error=float(resp.get("residualError", 0.0)),
        active_duration=float(resp.get("activeDuration", 0.0)),
        warnings=warns(resp),
    )
