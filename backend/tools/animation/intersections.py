from __future__ import annotations

from backend.app import mcp
from backend.bridge.client import UnityBridge
from backend.schemas.intersections import (
    BodyPenetrationEvent,
    SelfIntersectionResult,
)


@mcp.tool()
async def analyze_self_intersections(
    target_object_path: str,
    clip_path: str,
    sample_fps: int = 30,
    tolerance_meters: float = 0.02,
) -> SelfIntersectionResult:
    """
    Diagnoses character mesh self-intersections and body clipping across AnimationClip playback.

    Evaluates non-adjacent skeletal segment capsules (arms vs torso, thighs vs each other,
    hands vs hips) across uniformly sampled animation frames. Detects geometry interpenetration,
    identifying timestamps, colliding limb pairs, and penetration depths.

    Args:
        target_object_path: Scene path to character GameObject.
        clip_path: Project-relative path to the AnimationClip (.anim).
        sample_fps: Sampling frequency in frames per second (default 30).
        tolerance_meters: Distance penetration threshold in meters before flagging collision (default 0.02m).

    Returns:
        A SelfIntersectionResult detailing penetration events, max penetration depth, and clean interval percent.
    """
    async with UnityBridge() as bridge:
        resp = await bridge.analyze_self_intersections_native(
            target_object_path=target_object_path,
            clip_path=clip_path,
            sample_fps=sample_fps,
            tolerance_meters=tolerance_meters,
        )

    penetrations: list[BodyPenetrationEvent] = []
    for item in resp.get("penetrations", []):
        penetrations.append(
            BodyPenetrationEvent(
                time=float(item.get("time", 0.0)),
                limb_a=str(item.get("limbA", "")),
                limb_b=str(item.get("limbB", "")),
                penetration_depth_meters=float(item.get("penetrationDepthMeters", 0.0)),
                severity=str(item.get("severity", "warning")),
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
        warnings=list(resp.get("warnings", [])),
    )
