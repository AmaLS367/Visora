from typing import Literal

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    TwoBoneIKSolveResult,
    ViewportEffectorPlacementResult,
)
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, logger

_CAPABILITY_IK = "inverse_kinematics"
_CAPABILITY_VIEWPORT = "viewport_placement"


@mcp.tool()
async def solve_two_bone_ik(  # noqa: PLR0913
    target_object_path: str,
    target_position: list[float],
    effector: Literal["left_foot", "right_foot", "left_hand", "right_hand"] | None = None,
    root_bone: str | None = None,
    mid_bone: str | None = None,
    end_bone: str | None = None,
    target_rotation: list[float] | None = None,
    pole_vector: list[float] | None = None,
    space: Literal["world", "local", "camera"] = "world",
    camera_name: str = "Main Camera",
    weight: float = 1.0,
    apply_to_scene: bool = False,
    bake_to_clip: str | None = None,
    sample_time: float | None = None,
) -> TwoBoneIKSolveResult:
    """
    Solves analytical Two-Bone Inverse Kinematics for a 3-joint limb chain.

    Computes local and world Euler/Quaternion rotations using the Law of Cosines, with soft-extension
    damping near maximum reach to eliminate joint popping. Supports pole vector hints for bend direction
    control and end-effector orientation matching.

    Args:
        target_object_path: Scene hierarchy path to the target character GameObject.
        target_position: 3D target coordinates [x, y, z] to reach.
        effector: High-level limb identifier ("left_foot", "right_foot", "left_hand", "right_hand").
        root_bone: Explicit root bone path/name if not using standard effector (e.g. UpperLeg).
        mid_bone: Explicit mid bone path/name if not using standard effector (e.g. LowerLeg).
        end_bone: Explicit end bone path/name if not using standard effector (e.g. Foot).
        target_rotation: Optional target orientation for end effector (Euler [x,y,z] or Quat [x,y,z,w]).
        pole_vector: World position hint controlling the knee or elbow bend direction.
        space: Coordinate space for target_position: "world", "local", or "camera".
        camera_name: Camera name if space is "camera" (default: "Main Camera").
        weight: Blend weight between initial pose and IK solve (0.0 to 1.0, default: 1.0).
        apply_to_scene: If True, mutates scene transforms in Edit Mode with Undo support.
        bake_to_clip: Asset path to AnimationClip if baking rotations to curves (e.g. "Assets/Run.anim").
        sample_time: Timestamp (seconds) in AnimationClip where keys will be inserted if baking.

    Returns:
        A TwoBoneIKSolveResult detailing solved rotations, reachability, clamping, and residual error.
    """
    if len(target_position) < 3:
        return TwoBoneIKSolveResult(
            success=False,
            error="target_position must contain at least 3 coordinates [x, y, z]",
            target_object_path=target_object_path,
        )

    if bake_to_clip or apply_to_scene:
        edit_mode_err = await _require_edit_mode()
        if edit_mode_err:
            return TwoBoneIKSolveResult(
                success=False,
                error=edit_mode_err,
                target_object_path=target_object_path,
            )

    if not await _bridge_supports(_CAPABILITY_IK):
        return TwoBoneIKSolveResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_IK}'. Update Visora Unity package.",
            target_object_path=target_object_path,
        )

    try:
        resp = await animation_pkg.bridge.solve_two_bone_ik_native(
            target_path=target_object_path,
            target_position=target_position,
            effector=effector,
            root_bone=root_bone,
            mid_bone=mid_bone,
            end_bone=end_bone,
            target_rotation=target_rotation,
            pole_vector=pole_vector,
            space=space,
            camera_name=camera_name,
            weight=weight,
            apply_to_scene=apply_to_scene,
            bake_to_clip=bake_to_clip,
            sample_time=sample_time,
        )

        if not resp.get("success", False):
            return TwoBoneIKSolveResult(
                success=False,
                error=str(resp.get("error", "Failed to solve Two-Bone IK")),
                target_object_path=target_object_path,
                warnings=[str(w) for w in resp.get("warnings", [])],
            )

        return TwoBoneIKSolveResult(
            success=True,
            target_object_path=str(resp.get("targetObjectPath", target_object_path)),
            effector=resp.get("effector") or effector,
            root_bone=resp.get("rootBone"),
            mid_bone=resp.get("midBone"),
            end_bone=resp.get("endBone"),
            root_rotation_euler=resp.get("rootRotationEuler"),
            root_rotation_quaternion=resp.get("rootRotationQuaternion"),
            mid_rotation_euler=resp.get("midRotationEuler"),
            mid_rotation_quaternion=resp.get("midRotationQuaternion"),
            end_rotation_euler=resp.get("endRotationEuler"),
            end_rotation_quaternion=resp.get("endRotationQuaternion"),
            target_clamped=bool(resp.get("targetClamped", False)),
            reach_distance=float(resp.get("reachDistance", 0.0)),
            actual_distance=float(resp.get("actualDistance", 0.0)),
            position_residual=float(resp.get("positionResidual", 0.0)),
            rotation_residual_deg=float(resp.get("rotationResidualDeg", 0.0)),
            backup_id=resp.get("backupId"),
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error executing solve_two_bone_ik")
        return TwoBoneIKSolveResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            target_object_path=target_object_path,
        )


@mcp.tool()
async def place_effector_in_viewport(  # noqa: PLR0913
    target_object_path: str,
    viewport_x: float = 0.5,
    viewport_y: float = 0.5,
    camera_depth: float = 0.25,
    camera_name: str = "Main Camera",
    effector: Literal["left_foot", "right_foot", "left_hand", "right_hand"] | None = None,
    root_bone: str | None = None,
    mid_bone: str | None = None,
    end_bone: str | None = None,
    align_mode: Literal["face_camera", "match_camera_rotation", "keep_current", "custom"] = "face_camera",
    custom_rotation: list[float] | None = None,
    pole_vector: list[float] | None = None,
    weight: float = 1.0,
    apply_to_scene: bool = False,
    bake_to_clip: str | None = None,
    sample_time: float | None = None,
) -> ViewportEffectorPlacementResult:
    """
    Solves inverse camera projection to position an effector at an exact 2D camera viewport position and depth.

    Unprojects normalized viewport coordinates (u, v) and distance into world space using the camera's
    projection matrix, aligns effector orientation to face the lens (e.g. foot sole stamping onto camera glass),
    and solves Two-Bone IK with sub-pixel verification.

    Args:
        target_object_path: Scene hierarchy path to the character GameObject.
        viewport_x: Horizontal screen position (0.0 = left edge, 0.5 = center, 1.0 = right edge).
        viewport_y: Vertical screen position (0.0 = bottom edge, 0.5 = center, 1.0 = top edge).
        camera_depth: Distance from the camera lens in meters (e.g. 0.25m for close impact).
        camera_name: Name of the reference camera (default: "Main Camera").
        effector: Limb effector ("left_foot", "right_foot", "left_hand", "right_hand").
        root_bone: Explicit root bone path if not using humanoid effector.
        mid_bone: Explicit mid bone path if not using humanoid effector.
        end_bone: Explicit end bone path if not using humanoid effector.
        align_mode: Effector orientation mode: "face_camera" (sole/palm faces lens),
                    "match_camera_rotation", "keep_current", or "custom".
        custom_rotation: Custom orientation if align_mode is "custom" (Euler [x,y,z] or Quat [x,y,z,w]).
        pole_vector: World position hint controlling the knee or elbow bend direction.
        weight: Blend weight between initial pose and IK solve (0.0 to 1.0).
        apply_to_scene: If True, mutates scene transforms in Edit Mode.
        bake_to_clip: Asset path to AnimationClip if baking rotations.
        sample_time: Timestamp (seconds) in AnimationClip if baking.

    Returns:
        A ViewportEffectorPlacementResult with target and solved positions, screen residuals, and IK metrics.
    """
    if camera_depth <= 0.001:
        return ViewportEffectorPlacementResult(
            success=False,
            error="camera_depth must be greater than 0.001 meters",
            camera_name=camera_name,
            target_object_path=target_object_path,
        )

    if bake_to_clip or apply_to_scene:
        edit_mode_err = await _require_edit_mode()
        if edit_mode_err:
            return ViewportEffectorPlacementResult(
                success=False,
                error=edit_mode_err,
                camera_name=camera_name,
                target_object_path=target_object_path,
            )

    if not await _bridge_supports(_CAPABILITY_VIEWPORT):
        return ViewportEffectorPlacementResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_VIEWPORT}'. Update Visora Unity package.",
            camera_name=camera_name,
            target_object_path=target_object_path,
        )

    try:
        resp = await animation_pkg.bridge.place_effector_in_viewport_native(
            target_path=target_object_path,
            viewport_x=viewport_x,
            viewport_y=viewport_y,
            camera_depth=camera_depth,
            camera_name=camera_name,
            effector=effector,
            root_bone=root_bone,
            mid_bone=mid_bone,
            end_bone=end_bone,
            align_mode=align_mode,
            custom_rotation=custom_rotation,
            pole_vector=pole_vector,
            weight=weight,
            apply_to_scene=apply_to_scene,
            bake_to_clip=bake_to_clip,
            sample_time=sample_time,
        )

        if not resp.get("success", False):
            return ViewportEffectorPlacementResult(
                success=False,
                error=str(resp.get("error", "Failed to place effector in viewport")),
                camera_name=camera_name,
                target_object_path=target_object_path,
                warnings=[str(w) for w in resp.get("warnings", [])],
            )

        ik_data = resp.get("ikResult")
        ik_res: TwoBoneIKSolveResult | None = None
        if isinstance(ik_data, dict):
            ik_res = TwoBoneIKSolveResult(
                success=bool(ik_data.get("success", True)),
                error=ik_data.get("error"),
                target_object_path=target_object_path,
                effector=ik_data.get("effector"),
                root_bone=ik_data.get("rootBone"),
                mid_bone=ik_data.get("midBone"),
                end_bone=ik_data.get("endBone"),
                root_rotation_euler=ik_data.get("rootRotationEuler"),
                root_rotation_quaternion=ik_data.get("rootRotationQuaternion"),
                mid_rotation_euler=ik_data.get("midRotationEuler"),
                mid_rotation_quaternion=ik_data.get("midRotationQuaternion"),
                end_rotation_euler=ik_data.get("endRotationEuler"),
                end_rotation_quaternion=ik_data.get("endRotationQuaternion"),
                target_clamped=bool(ik_data.get("targetClamped", False)),
                reach_distance=float(ik_data.get("reachDistance", 0.0)),
                actual_distance=float(ik_data.get("actualDistance", 0.0)),
                position_residual=float(ik_data.get("positionResidual", 0.0)),
                rotation_residual_deg=float(ik_data.get("rotationResidualDeg", 0.0)),
                backup_id=ik_data.get("backupId"),
                warnings=[str(w) for w in ik_data.get("warnings", [])],
            )

        return ViewportEffectorPlacementResult(
            success=True,
            camera_name=camera_name,
            target_object_path=target_object_path,
            effector=effector,
            target_world_position=resp.get("targetWorldPosition") or [],
            solved_world_position=resp.get("solvedWorldPosition") or [],
            actual_viewport=resp.get("actualViewport") or [],
            screen_residual_pixels=resp.get("screenResidualPixels") or [],
            depth_residual_meters=float(resp.get("depthResidualMeters", 0.0)),
            is_in_frustum=bool(resp.get("isInFrustum", True)),
            is_clipped_by_near_plane=bool(resp.get("isClippedByNearPlane", False)),
            reach_distance=float(resp.get("reachDistance", 0.0)),
            actual_distance=float(resp.get("actualDistance", 0.0)),
            target_clamped=bool(resp.get("targetClamped", False)),
            ik_result=ik_res,
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error executing place_effector_in_viewport")
        return ViewportEffectorPlacementResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            camera_name=camera_name,
            target_object_path=target_object_path,
        )


__all__ = [
    "place_effector_in_viewport",
    "solve_two_bone_ik",
]
