import logging
from typing import Any, cast

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import (
    AnimationBindingCurve,
    AnimationEventInfo,
    ClipInspectorResult,
    SampleAnimationResult,
    SkeletonMapperResult,
    TransformPose,
)
from backend.tools.animation.analysis import (
    analyze_sampled_pose,
    detect_dangerous_curves,
)
from backend.tools.animation.scripts import (
    _inspect_clip_code,
    _sample_clip_code,
)

logger = logging.getLogger("backend.tools.animation")
bridge = UnityBridge()


@mcp.tool()
async def inspect_animation_clip(clip_path: str) -> ClipInspectorResult:
    """
    Inspects an AnimationClip's metadata, curves, bindings, and animation events in Unity project assets.
    Automatically detects dangerous curves (unexpected position, scale animations, static flat curves).

    Args:
        clip_path: Project-relative path to the AnimationClip (e.g. "Assets/Animations/Run.anim").

    Returns:
        A ClipInspectorResult containing clip details, bindings list, events, and dangerous curve diagnostics.
    """
    try:
        code = _inspect_clip_code(clip_path)
        resp = await bridge.execute_code(code)

        result_data = resp.get("result")
        if not isinstance(result_data, dict):
            # Sometimes AnkleBreaker returns result under "data" or top-level
            result_data = resp

        if not result_data.get("success", False):
            error_msg = str(result_data.get("error", "Unknown Unity inspection error"))
            logger.warning(f"Clip inspection failed for '{clip_path}': {error_msg}")
            return ClipInspectorResult(
                success=False,
                error=error_msg,
                clip_path=clip_path,
            )

        raw_bindings = result_data.get("bindings", [])
        bindings: list[AnimationBindingCurve] = []
        if isinstance(raw_bindings, list):
            for b in raw_bindings:
                if isinstance(b, dict):
                    bindings.append(
                        AnimationBindingCurve(
                            path=str(b.get("path", "")),
                            property_name=str(b.get("propertyName", "")),
                            type_name=str(b.get("typeName", "UnityEngine.Transform")),
                            curve_type=str(b.get("curveType", "unknown")),
                            keyframe_count=int(b.get("keyframeCount", 0)),
                            min_value=b.get("minValue"),
                            max_value=b.get("maxValue"),
                            start_value=b.get("startValue"),
                            end_value=b.get("endValue"),
                            is_constant=bool(b.get("isConstant", False)),
                        )
                    )

        raw_events = result_data.get("events", [])
        events: list[AnimationEventInfo] = []
        if isinstance(raw_events, list):
            for e in raw_events:
                if isinstance(e, dict):
                    events.append(
                        AnimationEventInfo(
                            time=float(e.get("time", 0.0)),
                            function_name=str(e.get("functionName", "")),
                            string_param=str(e.get("stringParam", "")),
                            float_param=float(e.get("floatParam", 0.0)),
                            int_param=int(e.get("intParam", 0)),
                        )
                    )

        length = float(result_data.get("length", 0.0))
        has_root_motion = bool(result_data.get("hasRootMotion", False))

        dangerous_curves, summary_metrics = detect_dangerous_curves(
            bindings=bindings,
            clip_length=length,
            has_root_motion=has_root_motion,
        )

        return ClipInspectorResult(
            success=True,
            clip_name=cast(str | None, result_data.get("clipName")),
            clip_path=cast(str | None, result_data.get("clipPath", clip_path)),
            length=length,
            fps=float(result_data.get("fps", 30.0)),
            loop_time=bool(result_data.get("loopTime", False)),
            wrap_mode=cast(str | None, result_data.get("wrapMode")),
            is_legacy=bool(result_data.get("isLegacy", False)),
            has_root_motion=has_root_motion,
            curves_count=len(bindings),
            events_count=len(events),
            bindings=bindings,
            dangerous_curves=dangerous_curves,
            events=events,
            summary_metrics=summary_metrics,
        )
    except Exception as e:
        logger.error(f"Error during inspect_animation_clip for '{clip_path}': {e}")
        return ClipInspectorResult(
            success=False,
            error=str(e),
            clip_path=clip_path,
        )


@mcp.tool()
async def clip_inspector(clip_path: str) -> ClipInspectorResult:
    """
    Inspects an animation clip's metadata, curves, and properties (alias for inspect_animation_clip).

    Args:
        clip_path: The project-relative path to the animation clip asset.

    Returns:
        A ClipInspectorResult containing animation duration, frame rate, loop configuration, and curve metrics.
    """
    res = await inspect_animation_clip(clip_path)
    return cast(ClipInspectorResult, res)


@mcp.tool()
async def sample_animation_clip(  # noqa: PLR0913
    target_game_object_path: str,
    clip_path: str,
    time: float | None = None,
    normalized_time: float | None = None,
    restore_pose_after: bool = True,
    track_transforms: list[str] | None = None,
) -> SampleAnimationResult:
    """
    Samples an AnimationClip on a GameObject at a specific timestamp or normalized time in the Unity scene.
    Inspects resulting transform hierarchy poses, root motion deltas, and validates for pose anomalies.
    Safely restores the original GameObject pose after sampling by default.

    Args:
        target_game_object_path: Hierarchy path in the active scene to the target GameObject.
        clip_path: Project asset path to the AnimationClip to sample.
        time: Timestamp in seconds at which to sample the clip.
        normalized_time: Normalized timestamp between 0.0 (start) and 1.0 (end). Used if time is omitted.
        restore_pose_after: If True (default), reverts all transform poses to rest state after sampling.
        track_transforms: Optional list of bone/transform paths relative to target to sample. If None, samples all children.

    Returns:
        A SampleAnimationResult with sampled transform poses, root motion displacement, and anomaly checks.
    """
    try:
        sample_timestamp = 0.0
        if time is not None:
            sample_timestamp = max(0.0, float(time))
        elif normalized_time is not None:
            # Inspect clip to get length
            inspect_res = await inspect_animation_clip(clip_path)
            clip_len = inspect_res.length if inspect_res.success and inspect_res.length else 1.0
            sample_timestamp = max(0.0, float(normalized_time) * clip_len)

        code = _sample_clip_code(
            target_game_object_path=target_game_object_path,
            clip_path=clip_path,
            time=sample_timestamp,
            restore_pose_after=restore_pose_after,
            tracked_bone_paths=track_transforms,
        )

        resp = await bridge.execute_code(code)
        result_data = resp.get("result")
        if not isinstance(result_data, dict):
            result_data = resp

        if not result_data.get("success", False):
            error_msg = str(result_data.get("error", "Failed to sample animation clip"))
            logger.warning(f"Animation sampling failed for '{target_game_object_path}': {error_msg}")
            return SampleAnimationResult(
                success=False,
                error=error_msg,
                clip_path=clip_path,
                target_game_object=target_game_object_path,
            )

        raw_transforms = result_data.get("sampledTransforms", {})
        sampled_transforms: dict[str, TransformPose] = {}

        if isinstance(raw_transforms, dict):
            for path_key, t in raw_transforms.items():
                if isinstance(t, dict):
                    sampled_transforms[path_key] = TransformPose(
                        path=str(t.get("path", path_key)),
                        name=str(t.get("name", "")),
                        local_position=list(t.get("localPosition", [0.0, 0.0, 0.0])),
                        local_rotation_euler=list(t.get("localRotationEuler", [0.0, 0.0, 0.0])),
                        local_scale=list(t.get("localScale", [1.0, 1.0, 1.0])),
                        world_position=t.get("worldPosition"),
                        world_rotation_euler=t.get("worldRotationEuler"),
                        world_scale=t.get("worldScale"),
                    )

        anomalies, warnings = analyze_sampled_pose(sampled_transforms)

        raw_root_delta = result_data.get("rootMotionDelta")
        root_motion_delta = list(raw_root_delta) if isinstance(raw_root_delta, list) else None

        return SampleAnimationResult(
            success=True,
            clip_name=cast(str | None, result_data.get("clipName")),
            clip_path=cast(str | None, result_data.get("clipPath", clip_path)),
            target_game_object=target_game_object_path,
            sample_time=sample_timestamp,
            normalized_time=normalized_time,
            pose_restored=bool(result_data.get("poseRestored", restore_pose_after)),
            sampled_transforms=sampled_transforms,
            root_motion_delta=root_motion_delta,
            anomalies_detected=anomalies,
            warnings=warnings,
        )
    except Exception as e:
        logger.error(f"Error during sample_animation_clip: {e}")
        return SampleAnimationResult(
            success=False,
            error=str(e),
            clip_path=clip_path,
            target_game_object=target_game_object_path,
        )


@mcp.tool()
async def analyze_animation_curves(clip_path: str) -> ClipInspectorResult:
    """
    Performs focused curve diagnostic inspection on an AnimationClip asset.

    Args:
        clip_path: Project asset path to the AnimationClip.

    Returns:
        A ClipInspectorResult with dangerous curve warnings and curve distribution metrics.
    """
    res = await inspect_animation_clip(clip_path)
    return cast(ClipInspectorResult, res)


@mcp.tool()
async def skeleton_mapper(root_transform_path: str) -> SkeletonMapperResult:
    """
    Validates and maps an avatar/character bone hierarchy relative to a root transform.
    (Stub for Roadmap item 5: Skeleton and rig intelligence).

    Args:
        root_transform_path: Hierarchical path in the active scene to the skeleton root GameObject.

    Returns:
        A SkeletonMapperResult detailing mapped transforms and missing required humanoid bones.
    """
    return SkeletonMapperResult(success=True)
