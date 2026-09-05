import json


def _lit(value: object) -> str:
    """A JSON literal is also a valid C# literal for str/float/int/bool/list/None (as null)."""
    return json.dumps(value)


def _float_array_lit(values: list[float] | None) -> str:
    return "null" if values is None else "new float[] { " + ", ".join(f"{v}f" for v in values) + " }"


def _list_keyframes_code(
    *,
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
) -> str:
    return f"""var result = Visora.Editor.Services.AnimationAuthoringService.ListKeyframes(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)});
return Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);
"""


def _set_keyframe_code(  # noqa: PLR0913
    *,
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
    time: float,
    values: list[float],
    tangent_mode: str | None,
    in_tangent: list[float] | None,
    out_tangent: list[float] | None,
    operation_id: str,
) -> str:
    return f"""var result = Visora.Editor.Services.AnimationAuthoringService.SetKeyframe(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {time}f, {_float_array_lit(values)}, {_lit(tangent_mode)},
    {_float_array_lit(in_tangent)}, {_float_array_lit(out_tangent)}, {_lit(operation_id)});
return Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);
"""


def _move_keyframe_code(  # noqa: PLR0913
    *,
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
    from_time: float,
    to_time: float,
    operation_id: str,
) -> str:
    return f"""var result = Visora.Editor.Services.AnimationAuthoringService.MoveKeyframe(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {from_time}f, {to_time}f, {_lit(operation_id)});
return Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);
"""


def _remove_keyframe_code(  # noqa: PLR0913
    *,
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
    time: float,
    operation_id: str,
) -> str:
    return f"""var result = Visora.Editor.Services.AnimationAuthoringService.RemoveKeyframe(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {time}f, {_lit(operation_id)});
return Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);
"""


def _hold_keyframe_code(  # noqa: PLR0913
    *,
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
    time: float,
    hold_until: float,
    value: list[float] | None,
    operation_id: str,
) -> str:
    return f"""var result = Visora.Editor.Services.AnimationAuthoringService.SetKeyframeHold(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {time}f, {hold_until}f, {_float_array_lit(value)}, {_lit(operation_id)});
return Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);
"""


def _create_event_code(  # noqa: PLR0913
    *,
    clip_path: str,
    time: float,
    function_name: str,
    string_param: str,
    float_param: float,
    int_param: int,
    operation_id: str,
) -> str:
    return f"""var result = Visora.Editor.Services.AnimationAuthoringService.CreateEvent(
    {_lit(clip_path)}, {time}f, {_lit(function_name)}, {_lit(string_param)},
    {float_param}f, {int_param}, {_lit(operation_id)});
return Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);
"""


def _remove_event_code(
    *,
    clip_path: str,
    time: float,
    function_name: str | None,
    operation_id: str,
) -> str:
    return f"""var result = Visora.Editor.Services.AnimationAuthoringService.RemoveEvent(
    {_lit(clip_path)}, {time}f, {_lit(function_name)}, {_lit(operation_id)});
return Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);
"""


def _list_backups_code(*, clip_path: str) -> str:
    return f"""var result = Visora.Editor.Services.AnimationBackupService.ListBackups({_lit(clip_path)});
return Visora.Editor.Services.AnimationBackupServiceDictionaries.ToDictionary(result);
"""


def _restore_backup_code(*, clip_path: str, backup_id: str, operation_id: str) -> str:
    return f"""var clip = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.AnimationClip>({_lit(clip_path)});
if (clip == null)
{{
    return new System.Collections.Generic.Dictionary<string, object> {{
        {{ "success", false }}, {{ "clipPath", {_lit(clip_path)} }},
        {{ "error", "AnimationClip not found at exact path " + {_lit(clip_path)} }},
    }};
}}
var result = Visora.Editor.Services.AnimationBackupService.RestoreBackup(
    clip, {_lit(clip_path)}, {_lit(backup_id)}, {_lit(operation_id)});
return Visora.Editor.Services.AnimationBackupServiceDictionaries.ToDictionary(result);
"""
