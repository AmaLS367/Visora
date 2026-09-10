from typing import Any

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    CharacterGazeResult,
    GazeJointRotation,
)
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, logger
from backend.tools.errors import bridge_retry_fields

_CAPABILITY_GAZE = "character_gaze"


def _parse_gaze_joints(raw_list: list[Any]) -> list[GazeJointRotation]:
    joints: list[GazeJointRotation] = []
    for item in raw_list:
        if isinstance(item, dict):
            joints.append(
                GazeJointRotation(
                    bone_name=str(item.get("boneName", "")),
                    local_euler=[float(x) for x in item.get("localEuler", [0.0, 0.0, 0.0])],
                    local_quaternion=[float(x) for x in item.get("localQuaternion", [0.0, 0.0, 0.0, 1.0])],
                    allocated_yaw_deg=float(item.get("allocatedYawDeg", 0.0)),
                    allocated_pitch_deg=float(item.get("allocatedPitchDeg", 0.0)),
                    was_clamped=bool(item.get("wasClamped", False)),
                )
            )
    return joints


@mcp.tool()
async def solve_character_gaze(  # noqa: PLR0911, PLR0913
    target_object_path: str,
    target_look_at_position: list[float] | None = None,
    target_transform_path: str | None = None,
    chest_weight: float = 0.15,
    neck_weight: float = 0.35,
    head_weight: float = 0.50,
    eyes_weight: float = 0.0,
    up_vector: list[float] | None = None,
    apply_to_scene: bool = False,
    bake_to_clip: str | None = None,
    sample_time: float | None = None,
) -> CharacterGazeResult:
    """
    Solves multi-joint character gaze and head/body orientation towards a target point or camera.

    Distributes rotation across Spine/Chest, Neck, Head, and Eyes with anatomical joint limits,
    avoiding unnatural stiff/doll-like poses and stabilizing up-vector posture.

    Args:
        target_object_path: Hierarchy path to the character GameObject.
        target_look_at_position: 3D world target position [x, y, z] to look at.
        target_transform_path: Alternative scene object path or "camera:Main Camera" to track.
        chest_weight: Fraction of gaze orientation allocated to chest/spine (default: 0.15).
        neck_weight: Fraction of gaze orientation allocated to neck (default: 0.35).
        head_weight: Fraction of gaze orientation allocated to head (default: 0.50).
        eyes_weight: Fraction of gaze orientation allocated to eyes (default: 0.0).
        up_vector: World up vector hint for head stabilization (default: [0, 1, 0]).
        apply_to_scene: If True, mutates scene transforms in Edit Mode with Undo support.
        bake_to_clip: Asset path to AnimationClip if baking rotations to curves.
        sample_time: Timestamp (seconds) in AnimationClip if baking.

    Returns:
        A CharacterGazeResult with per-joint rotations, total angular offset, and residual error.
    """
    if target_look_at_position is None and target_transform_path is None:
        return CharacterGazeResult(
            success=False,
            error="Either target_look_at_position or target_transform_path must be provided.",
            target_object_path=target_object_path,
        )

    if bake_to_clip and sample_time is None:
        return CharacterGazeResult(
            success=False,
            error="sample_time is required when bake_to_clip is set",
            target_object_path=target_object_path,
        )

    if bake_to_clip or apply_to_scene:
        edit_mode_err = await _require_edit_mode()
        if edit_mode_err:
            return CharacterGazeResult(
                success=False,
                error=edit_mode_err,
                target_object_path=target_object_path,
            )

    if not await _bridge_supports(_CAPABILITY_GAZE):
        return CharacterGazeResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_GAZE}'. Update Visora Unity package.",
            target_object_path=target_object_path,
        )

    try:
        resp = await animation_pkg.bridge.solve_character_gaze_native(
            target_path=target_object_path,
            target_look_at_position=target_look_at_position,
            target_transform_path=target_transform_path,
            chest_weight=chest_weight,
            neck_weight=neck_weight,
            head_weight=head_weight,
            eyes_weight=eyes_weight,
            up_vector=up_vector,
            apply_to_scene=apply_to_scene,
            bake_to_clip=bake_to_clip,
            sample_time=sample_time,
        )

        if not resp.get("success", False):
            return CharacterGazeResult(
                success=False,
                error=str(resp.get("error", "Failed to solve character gaze")),
                target_object_path=target_object_path,
                warnings=[str(w) for w in resp.get("warnings", [])],
            )

        joints = _parse_gaze_joints(resp.get("solvedJoints", []))

        return CharacterGazeResult(
            success=True,
            target_object_path=target_object_path,
            target_look_at_position=resp.get("targetLookAtPosition") or [],
            total_target_angle_deg=float(resp.get("totalTargetAngleDeg", 0.0)),
            is_target_behind_character=bool(resp.get("isTargetBehindCharacter", False)),
            was_clamped=bool(resp.get("wasClamped", False)),
            residual_gaze_error_deg=float(resp.get("residualGazeErrorDeg", 0.0)),
            solved_joints=joints,
            backup_id=resp.get("backupId"),
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error executing solve_character_gaze")
        return CharacterGazeResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            **bridge_retry_fields(exc),
            target_object_path=target_object_path,
        )


__all__ = [
    "solve_character_gaze",
]
