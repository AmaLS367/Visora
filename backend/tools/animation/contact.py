from typing import Any

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    BakeContactConstraintsResult,
    ContactAnalysisResult,
    ContactAnomaly,
    ContactEffectorDiagnostic,
    EffectorContactPhase,
)
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, logger

_CAPABILITY_CONTACT = "humanoid_contact_constraints"


def _parse_effector_diags(raw_list: list[Any]) -> list[ContactEffectorDiagnostic]:
    diags: list[ContactEffectorDiagnostic] = []
    for d in raw_list:
        if isinstance(d, dict):
            diags.append(
                ContactEffectorDiagnostic(
                    effector=str(d.get("effector", "")),
                    is_supported=bool(d.get("isSupported", False)),
                    root_bone=d.get("rootBone"),
                    mid_bone=d.get("midBone"),
                    end_bone=d.get("endBone"),
                    limb_length=float(d.get("limbLength", 0.0)),
                    blocker_reason=d.get("blockerReason"),
                )
            )
    return diags


def _parse_contact_phases(raw_list: list[Any]) -> list[EffectorContactPhase]:
    phases: list[EffectorContactPhase] = []
    for p in raw_list:
        if isinstance(p, dict):
            raw_pos = p.get("averagePosition", [0.0, 0.0, 0.0])
            avg_pos = [float(x) for x in raw_pos] if isinstance(raw_pos, list) else [0.0, 0.0, 0.0]
            phases.append(
                EffectorContactPhase(
                    effector=str(p.get("effector", "")),
                    start_time=float(p.get("startTime", 0.0)),
                    end_time=float(p.get("endTime", 0.0)),
                    duration=float(p.get("duration", 0.0)),
                    average_position=avg_pos,
                    is_sliding=bool(p.get("isSliding", False)),
                    slide_distance=float(p.get("slideDistance", 0.0)),
                )
            )
    return phases


def _parse_anomalies(raw_list: list[Any]) -> list[ContactAnomaly]:
    anomalies: list[ContactAnomaly] = []
    for a in raw_list:
        if isinstance(a, dict):
            anomalies.append(
                ContactAnomaly(
                    effector=str(a.get("effector", "")),
                    anomaly_type=a.get("anomalyType", "foot_sliding"),
                    start_time=float(a.get("startTime", 0.0)),
                    end_time=float(a.get("endTime", 0.0)),
                    severity=a.get("severity", "warning"),
                    value=float(a.get("value", 0.0)),
                    description=str(a.get("description", "")),
                )
            )
    return anomalies


@mcp.tool()
async def analyze_contact_constraints(  # noqa: PLR0913
    target_object_path: str,
    clip_path: str,
    effectors: list[str] | None = None,
    ground_mode: str = "plane",
    ground_plane_y: float = 0.0,
    velocity_threshold: float = 0.05,
    height_tolerance: float = 0.05,
) -> ContactAnalysisResult:
    """
    Analyzes contact dynamics (foot sliding, ground penetration, floating) and verifies IK chain support.

    Evaluates whether the skeleton has valid Two-Bone IK chains for feet/hands, samples the clip across
    time to identify continuous contact phases, and detects foot sliding distance and penetration depth.

    Args:
        target_object_path: Scene hierarchy path to the target character GameObject.
        clip_path: Asset path or name of the AnimationClip to evaluate.
        effectors: List of effectors to analyze (default: ["left_foot", "right_foot"]).
        ground_mode: Ground elevation mode: "plane" (fixed Y), "raycast" (scene colliders), or "auto" (detected).
        ground_plane_y: Reference elevation of the ground surface (default: 0.0).
        velocity_threshold: Maximum speed (m/s) to classify an effector as stationary / in contact (default: 0.05).
        height_tolerance: Vertical distance tolerance (m) to ground plane (default: 0.05).

    Returns:
        A ContactAnalysisResult with supported effectors, contact phases, and quantified anomalies.
    """
    if not await _bridge_supports(_CAPABILITY_CONTACT):
        return ContactAnalysisResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_CONTACT}'. Update Visora Unity package.",
            clip_path=clip_path,
            target_object_path=target_object_path,
        )

    try:
        resp = await animation_pkg.bridge.analyze_contact_constraints(
            target_path=target_object_path,
            clip_path=clip_path,
            effectors=effectors,
            ground_mode=ground_mode,
            ground_y=ground_plane_y,
            vel_threshold=velocity_threshold,
            height_tol=height_tolerance,
        )
        if not resp.get("success", False):
            return ContactAnalysisResult(
                success=False,
                error=str(resp.get("error", "Failed to analyze contact constraints")),
                clip_path=clip_path,
                target_object_path=target_object_path,
            )

        supported = _parse_effector_diags(resp.get("supportedEffectors", []))
        unsupported = _parse_effector_diags(resp.get("unsupportedEffectors", []))
        phases = _parse_contact_phases(resp.get("contactPhases", []))
        anomalies = _parse_anomalies(resp.get("anomalies", []))

        return ContactAnalysisResult(
            success=True,
            clip_path=clip_path,
            target_object_path=target_object_path,
            supported_effectors=supported,
            unsupported_effectors=unsupported,
            contact_phases=phases,
            anomalies=anomalies,
            total_slide_distance=float(resp.get("totalSlideDistance", 0.0)),
            max_ground_penetration=float(resp.get("maxGroundPenetration", 0.0)),
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error analyzing contact constraints")
        return ContactAnalysisResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            clip_path=clip_path,
            target_object_path=target_object_path,
        )


@mcp.tool()
async def bake_contact_constraints(  # noqa: PLR0913
    clip_path: str,
    target_object_path: str,
    output_clip_path: str | None = None,
    effectors: list[str] | None = None,
    ground_plane_y: float = 0.0,
    fix_foot_sliding: bool = True,
    fix_penetration: bool = True,
    operation_id: str | None = None,
) -> BakeContactConstraintsResult:
    """
    Applies 3D Two-Bone IK during contact phases to eliminate foot sliding and ground penetration.

    Solves analytical inverse kinematics for affected limbs, locks foot drift during contact intervals,
    and bakes the resulting rotations into AnimationClip curves with pre-mutation backup and Undo support.
    If the clip is an embedded/read-only FBX sub-asset, automatically clones to a writable .anim asset.

    Args:
        clip_path: Asset path or name of the AnimationClip to bake.
        target_object_path: Scene hierarchy path to the target character GameObject.
        output_clip_path: Destination path for the baked clip (optional, required if source is read-only).
        effectors: Limbs to bake (default: ["left_foot", "right_foot"]).
        ground_plane_y: Ground plane elevation in world units (default: 0.0).
        fix_foot_sliding: If True, locks horizontal position of the foot during contact phases.
        fix_penetration: If True, prevents feet from dipping below ground_plane_y.
        operation_id: Optional client-assigned idempotency token for the operation.

    Returns:
        A BakeContactConstraintsResult detailing modified curves, backup ID, and slide reduction percentage.
    """
    edit_mode_err = await _require_edit_mode()
    if edit_mode_err:
        return BakeContactConstraintsResult(
            success=False,
            error=edit_mode_err,
            source_clip_path=clip_path,
        )

    if not await _bridge_supports(_CAPABILITY_CONTACT):
        return BakeContactConstraintsResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_CONTACT}'. Update Visora Unity package.",
            source_clip_path=clip_path,
        )

    try:
        resp = await animation_pkg.bridge.bake_contact_constraints(
            target_path=target_object_path,
            clip_path=clip_path,
            output_clip_path=output_clip_path,
            effectors=effectors,
            ground_y=ground_plane_y,
            fix_sliding=fix_foot_sliding,
            fix_penetration=fix_penetration,
            operation_id=operation_id,
        )
        if not resp.get("success", False):
            return BakeContactConstraintsResult(
                success=False,
                error=str(resp.get("error", "Failed to bake contact constraints")),
                source_clip_path=clip_path,
                output_clip_path=output_clip_path,
            )

        return BakeContactConstraintsResult(
            success=True,
            source_clip_path=str(resp.get("sourceClipPath", clip_path)),
            output_clip_path=str(resp.get("outputClipPath", output_clip_path or clip_path)),
            backup_id=resp.get("backupId"),
            effectors_baked=[str(e) for e in resp.get("effectorsBaked", [])],
            keyframes_modified_count=int(resp.get("keyframesModifiedCount", 0)),
            slide_reduction_percent=float(resp.get("slideReductionPercent", 0.0)),
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error baking contact constraints")
        return BakeContactConstraintsResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            source_clip_path=clip_path,
            output_clip_path=output_clip_path,
        )


__all__ = [
    "analyze_contact_constraints",
    "bake_contact_constraints",
]
