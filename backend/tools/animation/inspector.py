from typing import Any, cast

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    AnimationBindingCurve,
    AnimationEventInfo,
    ClipInspectorResult,
)
from backend.tools.animation.analysis import detect_dangerous_curves
from backend.tools.animation.scripts import _inspect_clip_code


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
        resp = await animation_pkg.bridge.execute_capability(code)

        result_data = resp.get("result")
        if not isinstance(result_data, dict):
            # Sometimes AnkleBreaker returns result under "data" or top-level
            result_data = resp

        if not result_data.get("success", False):
            error_msg = str(result_data.get("error", "Unknown Unity inspection error"))
            animation_pkg.logger.warning(f"Clip inspection failed for '{clip_path}': {error_msg}")
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
        animation_pkg.logger.error(f"Error during inspect_animation_clip for '{clip_path}': {e}")
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
    return await inspect_animation_clip(clip_path)


@mcp.tool()
async def analyze_animation_curves(clip_path: str) -> ClipInspectorResult:
    """
    Performs focused curve diagnostic inspection on an AnimationClip asset.

    Args:
        clip_path: Project asset path to the AnimationClip.

    Returns:
        A ClipInspectorResult with dangerous curve warnings and curve distribution metrics.
    """
    return await inspect_animation_clip(clip_path)


__all__ = [
    "analyze_animation_curves",
    "clip_inspector",
    "inspect_animation_clip",
]
