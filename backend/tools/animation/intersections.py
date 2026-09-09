import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas.intersections import BodyPenetrationEvent, SelfIntersectionResult
from backend.tools.animation.common import _bridge_supports, coerce_literal, logger, warns

_CAPABILITY = "self_intersection_analysis"
_SEVERITY = {"critical", "warning"}


@mcp.tool()
async def analyze_self_intersections(
    target_object_path: str,
    clip_path: str,
    sample_fps: int = 30,
    tolerance_meters: float = 0.02,
) -> SelfIntersectionResult:
    """
    Diagnoses character mesh self-intersections and body clipping across AnimationClip playback.

    Builds skeletal capsule proxies generically from the rig hierarchy (no humanoid assumption)
    and tests every non-adjacent segment pair across uniformly sampled animation frames. Detects
    geometry interpenetration, identifying timestamps, colliding segment pairs, and penetration
    depths. Rigs the analyzer cannot model (fewer than 2 capsule proxies) return success=False
    rather than a misleading "100% clean" pass.

    Args:
        target_object_path: Scene path to character GameObject.
        clip_path: Project-relative path to the AnimationClip (.anim).
        sample_fps: Sampling frequency in frames per second (default 30).
        tolerance_meters: Distance penetration threshold in meters before flagging collision (default 0.02m).

    Returns:
        A SelfIntersectionResult detailing penetration events, max penetration depth, and clean interval percent.
    """
    if sample_fps <= 0:
        return SelfIntersectionResult(
            success=False,
            error="sample_fps must be greater than 0.",
            target_object_path=target_object_path,
            clip_path=clip_path,
        )
    if tolerance_meters <= 0:
        return SelfIntersectionResult(
            success=False,
            error="tolerance_meters must be greater than 0.",
            target_object_path=target_object_path,
            clip_path=clip_path,
        )

    if not await _bridge_supports(_CAPABILITY):
        return SelfIntersectionResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY}'. Update Visora Unity package.",
            target_object_path=target_object_path,
            clip_path=clip_path,
        )

    try:
        resp = await animation_pkg.bridge.analyze_self_intersections_native(
            target_object_path=target_object_path,
            clip_path=clip_path,
            sample_fps=sample_fps,
            tolerance_meters=tolerance_meters,
        )
    except Exception as exc:
        logger.exception("Error executing analyze_self_intersections")
        return SelfIntersectionResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            target_object_path=target_object_path,
            clip_path=clip_path,
        )

    result_warnings = warns(resp)
    penetrations: list[BodyPenetrationEvent] = []
    for item in resp.get("penetrations") or []:
        if not isinstance(item, dict):
            continue
        penetrations.append(
            BodyPenetrationEvent(
                time=float(item.get("time", 0.0)),
                limb_a=str(item.get("limbA", "")),
                limb_b=str(item.get("limbB", "")),
                penetration_depth_meters=float(item.get("penetrationDepthMeters", 0.0)),
                severity=coerce_literal(item.get("severity"), _SEVERITY, result_warnings, field="severity"),
                description=str(item.get("description", "")),
            )
        )

    return SelfIntersectionResult(
        success=bool(resp.get("success", False)),
        error=resp.get("error"),
        target_object_path=str(resp.get("targetObjectPath", target_object_path)),
        clip_path=str(resp.get("clipPath", clip_path)),
        intersections_found=int(resp.get("intersectionsFound", len(penetrations))),
        sample_count=int(resp.get("sampleCount", 0)),
        clean_interval_percent=float(resp.get("cleanIntervalPercent", 100.0)),
        max_penetration_depth=float(resp.get("maxPenetrationDepth", 0.0)),
        penetrations=penetrations,
        warnings=result_warnings,
    )
