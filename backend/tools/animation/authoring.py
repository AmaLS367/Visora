from typing import cast

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    AnimationKeyframeInfo,
    ListAnimationKeyframesResult,
)
from backend.tools.animation.common import _bridge_supports
from backend.tools.errors import bridge_error

_UNSUPPORTED_ERROR = "animation_authoring requires the Visora Unity package installed in the Unity project."


async def _authoring_supported() -> bool:
    return await _bridge_supports("animation_authoring")


@mcp.tool()
async def list_animation_keyframes(
    clip_path: str, target_path: str, type_name: str, property_name: str
) -> ListAnimationKeyframesResult:
    """
    Lists every keyframe of one logical property (e.g. "m_LocalPosition") across all its
    resolved channels. Read `channels`/`keyframes` before calling any write tool on this
    property, since move/remove address a key by time, not index.

    Returns:
        ListAnimationKeyframesResult containing resolved keyframes and channel mappings.
    """
    try:
        if not await _authoring_supported():
            return ListAnimationKeyframesResult(success=False, error=_UNSUPPORTED_ERROR, clip_path=clip_path)

        payload = await animation_pkg.bridge.list_keyframes_native(clip_path, target_path, type_name, property_name)

        keyframes = [
            AnimationKeyframeInfo(
                time=float(k["time"]),
                values=[float(v) for v in k["values"]],
                exact=[bool(e) for e in k["exact"]],
                in_tangents=[float(t) for t in k["inTangents"]],
                out_tangents=[float(t) for t in k["outTangents"]],
                tangent_mode=str(k["tangentMode"]),
            )
            for k in payload.get("keyframes", [])
        ]
        return ListAnimationKeyframesResult(
            success=bool(payload.get("success", False)),
            error=cast("str | None", payload.get("error")),
            clip_path=cast("str | None", payload.get("clipPath", clip_path)),
            target_path=cast("str | None", payload.get("targetPath", target_path)),
            type_name=cast("str | None", payload.get("typeName", type_name)),
            property_name=cast("str | None", payload.get("propertyName", property_name)),
            channels=[str(c) for c in payload.get("channels", [])],
            keyframes=keyframes,
        )
    except Exception as e:
        animation_pkg.logger.error("Error during list_animation_keyframes for '%s': %s", clip_path, e)
        return ListAnimationKeyframesResult(**bridge_error(e), clip_path=clip_path)


__all__ = [
    "list_animation_keyframes",
]
