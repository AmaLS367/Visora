from typing import Any, cast

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.config import get_settings
from backend.schemas import (
    SampleAnimationResult,
    TransformPose,
)
from backend.tools.animation.analysis import analyze_sampled_pose
from backend.tools.animation.inspector import inspect_animation_clip
from backend.tools.animation.scripts import _sample_clip_code


@mcp.tool()
async def sample_animation_clip(  # noqa: PLR0913
    target_game_object_path: str,
    clip_path: str,
    time: float | None = None,
    normalized_time: float | None = None,
    restore_pose_after: bool = True,
    track_transforms: list[str] | None = None,
    max_transforms: int | None = None,
) -> SampleAnimationResult:
    """
    Samples an AnimationClip on a GameObject at a specific timestamp or normalized time in the Unity scene.
    Inspects resulting transform hierarchy poses, root motion deltas, and validates for pose anomalies.
    Safely restores the original GameObject pose after sampling by default. Truncates full transforms dict
    to protect context window; pass track_transforms or max_transforms for specific bones.

    Args:
        target_game_object_path: Hierarchy path in the active scene to the target GameObject.
        clip_path: Project asset path to the AnimationClip to sample.
        time: Timestamp in seconds at which to sample the clip.
        normalized_time: Normalized timestamp between 0.0 (start) and 1.0 (end). Used if time is omitted.
        restore_pose_after: If True (default), reverts all transform poses to rest state after sampling.
        track_transforms: Optional list of bone/transform paths relative to target to sample. If None, samples all children.
        max_transforms: Optional maximum number of transforms to return in sampled_transforms (defaults to DIAGNOSTIC_MAX_TRANSFORMS).

    Returns:
        A SampleAnimationResult with sampled transform poses, root motion displacement, and anomaly checks.
    """
    try:
        sample_timestamp = 0.0
        if time is not None:
            sample_timestamp = max(0.0, time)
        elif normalized_time is not None:
            # Inspect clip to get length
            inspect_res = await inspect_animation_clip(clip_path)
            clip_len = inspect_res.length if inspect_res.success and inspect_res.length else 1.0
            sample_timestamp = max(0.0, normalized_time * clip_len)

        code = _sample_clip_code(
            target_game_object_path=target_game_object_path,
            clip_path=clip_path,
            time=sample_timestamp,
            restore_pose_after=restore_pose_after,
            tracked_bone_paths=track_transforms,
        )

        resp = await animation_pkg.bridge.execute_capability(code)
        result_data = resp.get("result")
        if not isinstance(result_data, dict):
            result_data = resp

        if not result_data.get("success", False):
            error_msg = str(result_data.get("error", "Failed to sample animation clip"))
            animation_pkg.logger.warning(f"Animation sampling failed for '{target_game_object_path}': {error_msg}")
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

        if track_transforms is None:
            settings = get_settings()
            limit = max_transforms if max_transforms is not None else settings.diagnostic_max_transforms
            if limit is not None and len(sampled_transforms) > limit:
                # Prioritize anomalous/warning transforms and root/shallow bones
                problem_notes = anomalies + warnings
                priority_keys: list[str] = [
                    k
                    for k in sampled_transforms
                    if any(f"({k})" in note or f"'{sampled_transforms[k].name}'" in note for note in problem_notes)
                ]
                remaining_keys = sorted(
                    [k for k in sampled_transforms if k not in priority_keys],
                    key=lambda p: (p.count("/"), len(p)),
                )
                selected_keys = (priority_keys + remaining_keys)[:limit]
                limited_transforms = {k: sampled_transforms[k] for k in selected_keys}
                warnings.append(
                    f"Showing {len(limited_transforms)} of {len(sampled_transforms)} transforms in sampled_transforms. "
                    "Specify track_transforms or max_transforms to inspect specific bones."
                )
                sampled_transforms = limited_transforms

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
        animation_pkg.logger.error(f"Error during sample_animation_clip: {e}")
        return SampleAnimationResult(
            success=False,
            error=str(e),
            clip_path=clip_path,
            target_game_object=target_game_object_path,
        )


__all__ = ["sample_animation_clip"]
