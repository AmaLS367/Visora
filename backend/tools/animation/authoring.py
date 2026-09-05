import uuid
from typing import Any, cast

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    AnimationClipEditResult,
    AnimationEventEditResult,
    AnimationKeyframeInfo,
    ListAnimationKeyframesResult,
)
from backend.tools.animation.authoring_scripts import (
    _create_event_code,
    _hold_keyframe_code,
    _list_keyframes_code,
    _move_keyframe_code,
    _remove_event_code,
    _remove_keyframe_code,
    _set_keyframe_code,
)
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, _unwrap_legacy_result


def _normalize_values(value: float | list[float]) -> list[float]:
    return value if isinstance(value, list) else [value]


async def _authoring_supported() -> bool:
    return await _bridge_supports("animation_authoring")


def _clip_edit_result(payload: dict[str, Any], default_clip_path: str | None = None) -> AnimationClipEditResult:
    success = bool(payload.get("success", False))
    raw_undo = payload.get("undoGroupId")
    undo_group_id: int | None = int(raw_undo) if raw_undo is not None and int(raw_undo) > 0 and success else None
    return AnimationClipEditResult(
        success=success,
        error=cast("str | None", payload.get("error")),
        clip_path=cast("str | None", payload.get("clipPath") or default_clip_path),
        target_path=cast("str | None", payload.get("targetPath")),
        type_name=cast("str | None", payload.get("typeName")),
        property_name=cast("str | None", payload.get("propertyName")),
        channels_affected=[str(c) for c in payload.get("channelsAffected", [])],
        curve_created=bool(payload.get("curveCreated", False)),
        time=float(payload["time"]) if payload.get("hasTime") and payload.get("time") is not None else None,
        previous_time=float(payload["previousTime"])
        if payload.get("hasPreviousTime") and payload.get("previousTime") is not None
        else None,
        keys_cleared=[float(k) for k in payload.get("keysCleared", [])],
        backup_id=cast("str | None", payload.get("backupId")),
        undo_group_id=undo_group_id,
        warnings=[str(w) for w in payload.get("warnings", [])],
    )


def _event_edit_result(payload: dict[str, Any], default_clip_path: str | None = None) -> AnimationEventEditResult:
    success = bool(payload.get("success", False))
    raw_undo = payload.get("undoGroupId")
    undo_group_id: int | None = int(raw_undo) if raw_undo is not None and int(raw_undo) > 0 and success else None
    return AnimationEventEditResult(
        success=success,
        error=cast("str | None", payload.get("error")),
        clip_path=cast("str | None", payload.get("clipPath") or default_clip_path),
        time=float(payload["time"]) if payload.get("hasTime") and payload.get("time") is not None else None,
        function_name=cast("str | None", payload.get("functionName")),
        events_affected=int(payload.get("eventsAffected", 0)),
        backup_id=cast("str | None", payload.get("backupId")),
        undo_group_id=undo_group_id,
        warnings=[str(w) for w in payload.get("warnings", [])],
    )


@mcp.tool()
async def list_animation_keyframes(
    clip_path: str, target_path: str, type_name: str, property_name: str
) -> ListAnimationKeyframesResult:
    """
    Lists every keyframe of one logical property (e.g. "m_LocalPosition") across all its
    resolved channels. Read `channels`/`keyframes` before calling any write tool on this
    property, since move/remove address a key by time, not index.
    """
    try:
        if await _authoring_supported():
            payload = await animation_pkg.bridge.list_keyframes_native(clip_path, target_path, type_name, property_name)
        else:
            code = _list_keyframes_code(
                clip_path=clip_path, target_path=target_path, type_name=type_name, property_name=property_name
            )
            payload = _unwrap_legacy_result(await animation_pkg.bridge.execute_code(code))

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
        return ListAnimationKeyframesResult(success=False, error=str(e), clip_path=clip_path)


@mcp.tool()
async def set_animation_keyframe(  # noqa: PLR0913
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
    time: float,
    value: float | list[float],
    tangent_mode: str | None = None,
    in_tangent: float | list[float] | None = None,
    out_tangent: float | list[float] | None = None,
) -> AnimationClipEditResult:
    """
    Upserts a keyframe on a logical property, creating the curve if it does not exist yet.
    `tangent_mode` left as None preserves an existing key's tangents and defaults to "smooth"
    only when creating a brand new key. Writes a VisoraBackups/ snapshot before editing.
    """
    try:
        edit_mode_error = await _require_edit_mode()
        if edit_mode_error is not None:
            return AnimationClipEditResult(success=False, error=edit_mode_error, clip_path=clip_path)

        values = _normalize_values(value)
        in_tangents = _normalize_values(in_tangent) if in_tangent is not None else None
        out_tangents = _normalize_values(out_tangent) if out_tangent is not None else None

        if await _authoring_supported():
            payload = await animation_pkg.bridge.set_keyframe_native(
                clip_path=clip_path,
                target_path=target_path,
                type_name=type_name,
                property_name=property_name,
                time=time,
                values=values,
                tangent_mode=tangent_mode,
                in_tangent=in_tangents,
                out_tangent=out_tangents,
            )
        else:
            code = _set_keyframe_code(
                clip_path=clip_path,
                target_path=target_path,
                type_name=type_name,
                property_name=property_name,
                time=time,
                values=values,
                tangent_mode=tangent_mode,
                in_tangent=in_tangents,
                out_tangent=out_tangents,
                operation_id=str(uuid.uuid4()),
            )
            payload = _unwrap_legacy_result(await animation_pkg.bridge.execute_code(code))

        return _clip_edit_result(payload, default_clip_path=clip_path)
    except Exception as e:
        animation_pkg.logger.error("Error during set_animation_keyframe for '%s': %s", clip_path, e)
        return AnimationClipEditResult(success=False, error=str(e), clip_path=clip_path)


@mcp.tool()
async def move_animation_keyframe(  # noqa: PLR0913
    clip_path: str, target_path: str, type_name: str, property_name: str, from_time: float, to_time: float
) -> AnimationClipEditResult:
    """Moves an existing keyframe to a new time, preserving its value and tangents."""
    try:
        edit_mode_error = await _require_edit_mode()
        if edit_mode_error is not None:
            return AnimationClipEditResult(success=False, error=edit_mode_error, clip_path=clip_path)

        if await _authoring_supported():
            payload = await animation_pkg.bridge.move_keyframe_native(
                clip_path, target_path, type_name, property_name, from_time, to_time
            )
        else:
            code = _move_keyframe_code(
                clip_path=clip_path,
                target_path=target_path,
                type_name=type_name,
                property_name=property_name,
                from_time=from_time,
                to_time=to_time,
                operation_id=str(uuid.uuid4()),
            )
            payload = _unwrap_legacy_result(await animation_pkg.bridge.execute_code(code))
        return _clip_edit_result(payload, default_clip_path=clip_path)
    except Exception as e:
        animation_pkg.logger.error("Error during move_animation_keyframe for '%s': %s", clip_path, e)
        return AnimationClipEditResult(success=False, error=str(e), clip_path=clip_path)


@mcp.tool()
async def remove_animation_keyframe(
    clip_path: str, target_path: str, type_name: str, property_name: str, time: float
) -> AnimationClipEditResult:
    """Removes the keyframe nearest `time` (within half a frame) across every resolved channel."""
    try:
        edit_mode_error = await _require_edit_mode()
        if edit_mode_error is not None:
            return AnimationClipEditResult(success=False, error=edit_mode_error, clip_path=clip_path)

        if await _authoring_supported():
            payload = await animation_pkg.bridge.remove_keyframe_native(
                clip_path, target_path, type_name, property_name, time
            )
        else:
            code = _remove_keyframe_code(
                clip_path=clip_path,
                target_path=target_path,
                type_name=type_name,
                property_name=property_name,
                time=time,
                operation_id=str(uuid.uuid4()),
            )
            payload = _unwrap_legacy_result(await animation_pkg.bridge.execute_code(code))
        return _clip_edit_result(payload, default_clip_path=clip_path)
    except Exception as e:
        animation_pkg.logger.error("Error during remove_animation_keyframe for '%s': %s", clip_path, e)
        return AnimationClipEditResult(success=False, error=str(e), clip_path=clip_path)


@mcp.tool()
async def set_keyframe_hold(  # noqa: PLR0913
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
    time: float,
    hold_until: float,
    value: float | list[float] | None = None,
) -> AnimationClipEditResult:
    """
    Freezes a property's value across [time, hold_until]: clears any keys strictly between the
    two boundaries and writes matching step-tangent keys at both, so nothing in the cleared
    range can still interpolate through a stale old key.
    """
    try:
        edit_mode_error = await _require_edit_mode()
        if edit_mode_error is not None:
            return AnimationClipEditResult(success=False, error=edit_mode_error, clip_path=clip_path)

        values = _normalize_values(value) if value is not None else None
        if await _authoring_supported():
            payload = await animation_pkg.bridge.hold_keyframe_native(
                clip_path, target_path, type_name, property_name, time, hold_until, values
            )
        else:
            code = _hold_keyframe_code(
                clip_path=clip_path,
                target_path=target_path,
                type_name=type_name,
                property_name=property_name,
                time=time,
                hold_until=hold_until,
                value=values,
                operation_id=str(uuid.uuid4()),
            )
            payload = _unwrap_legacy_result(await animation_pkg.bridge.execute_code(code))
        return _clip_edit_result(payload, default_clip_path=clip_path)
    except Exception as e:
        animation_pkg.logger.error("Error during set_keyframe_hold for '%s': %s", clip_path, e)
        return AnimationClipEditResult(success=False, error=str(e), clip_path=clip_path)


@mcp.tool()
async def create_animation_event(  # noqa: PLR0913
    clip_path: str,
    time: float,
    function_name: str,
    string_param: str = "",
    float_param: float = 0.0,
    int_param: int = 0,
) -> AnimationEventEditResult:
    """
    Adds an AnimationEvent. Camera recoil, hit flashes, and hit-stop are authored this way, at
    the same `time` as the motion key they accompany — one clip, one authoritative timestamp.
    """
    try:
        edit_mode_error = await _require_edit_mode()
        if edit_mode_error is not None:
            return AnimationEventEditResult(success=False, error=edit_mode_error, clip_path=clip_path)

        if await _authoring_supported():
            payload = await animation_pkg.bridge.create_event_native(
                clip_path, time, function_name, string_param, float_param, int_param
            )
        else:
            code = _create_event_code(
                clip_path=clip_path,
                time=time,
                function_name=function_name,
                string_param=string_param,
                float_param=float_param,
                int_param=int_param,
                operation_id=str(uuid.uuid4()),
            )
            payload = _unwrap_legacy_result(await animation_pkg.bridge.execute_code(code))
        return _event_edit_result(payload, default_clip_path=clip_path)
    except Exception as e:
        animation_pkg.logger.error("Error during create_animation_event for '%s': %s", clip_path, e)
        return AnimationEventEditResult(success=False, error=str(e), clip_path=clip_path)


@mcp.tool()
async def remove_animation_event(
    clip_path: str, time: float, function_name: str | None = None
) -> AnimationEventEditResult:
    """Removes every AnimationEvent near `time`, optionally filtered to one function name."""
    try:
        edit_mode_error = await _require_edit_mode()
        if edit_mode_error is not None:
            return AnimationEventEditResult(success=False, error=edit_mode_error, clip_path=clip_path)

        if await _authoring_supported():
            payload = await animation_pkg.bridge.remove_event_native(clip_path, time, function_name)
        else:
            code = _remove_event_code(
                clip_path=clip_path, time=time, function_name=function_name, operation_id=str(uuid.uuid4())
            )
            payload = _unwrap_legacy_result(await animation_pkg.bridge.execute_code(code))
        return _event_edit_result(payload, default_clip_path=clip_path)
    except Exception as e:
        animation_pkg.logger.error("Error during remove_animation_event for '%s': %s", clip_path, e)
        return AnimationEventEditResult(success=False, error=str(e), clip_path=clip_path)


__all__ = [
    "create_animation_event",
    "list_animation_keyframes",
    "move_animation_keyframe",
    "remove_animation_event",
    "remove_animation_keyframe",
    "set_animation_keyframe",
    "set_keyframe_hold",
]
