import json

from backend.tools.animation._shared_csharp import extract_as_local_function

_AUTHORING_CS = "AnimationAuthoringService.cs"
_BACKUP_CS = "AnimationBackupService.cs"


def _lit(value: object) -> str:
    """A JSON literal is also a valid C# literal for str/float/int/bool/list/None (as null)."""
    return json.dumps(value)


def _float_array_lit(values: list[float] | None) -> str:
    return "null" if values is None else "new float[] { " + ", ".join(f"{v}f" for v in values) + " }"


def _bool_lit(value: bool) -> str:
    return "true" if value else "false"


def _preamble(*region_names: tuple[str, str]) -> str:
    """Concatenates extracted regions in a fixed order, once per snippet."""
    return "\n".join(extract_as_local_function(filename, name) for filename, name in region_names)


_KEYFRAME_PRIMITIVES = (
    (_BACKUP_CS, "PathAndModeGuards"),
    (_BACKUP_CS, "IdempotencyCache"),
    (_BACKUP_CS, "WriteBackup"),
    (_AUTHORING_CS, "ResolveComponentType"),
    (_AUTHORING_CS, "ResolveChannels"),
    (_AUTHORING_CS, "MapTangentMode"),
    (_AUTHORING_CS, "FindKeyIndexNearTime"),
    (_AUTHORING_CS, "KeyframeHelpers"),
)

_EVENT_PRIMITIVES = (
    (_BACKUP_CS, "PathAndModeGuards"),
    (_BACKUP_CS, "IdempotencyCache"),
    (_BACKUP_CS, "WriteBackup"),
)

_BACKUP_PRIMITIVES = (
    (_BACKUP_CS, "PathAndModeGuards"),
    (_BACKUP_CS, "IdempotencyCache"),
)


def _to_dictionary_clip_edit_result_code() -> str:
    return """
System.Collections.Generic.Dictionary<string, object> ToDictionary(AnimationClipEditResult r)
{
    var dict = new System.Collections.Generic.Dictionary<string, object>
    {
        { "success", r.success }, { "clipPath", r.clipPath }, { "targetPath", r.targetPath },
        { "typeName", r.typeName }, { "propertyName", r.propertyName },
        { "channelsAffected", r.channelsAffected }, { "curveCreated", r.curveCreated },
        { "hasTime", r.hasTime }, { "hasPreviousTime", r.hasPreviousTime },
        { "keysCleared", r.keysCleared }, { "backupId", r.backupId }, { "undoGroupId", r.undoGroupId },
        { "warnings", r.warnings },
    };
    if (r.hasTime) dict["time"] = r.time;
    if (r.hasPreviousTime) dict["previousTime"] = r.previousTime;
    if (r.error != null) dict["error"] = r.error;
    return dict;
}
"""


def _to_dictionary_list_keyframes_result_code() -> str:
    return """
System.Collections.Generic.Dictionary<string, object> ToDictionary(ListAnimationKeyframesResult r)
{
    var keyframes = new System.Collections.Generic.List<object>();
    foreach (var k in r.keyframes)
    {
        keyframes.Add(new System.Collections.Generic.Dictionary<string, object>
        {
            { "time", k.time }, { "values", k.values }, { "exact", k.exact },
            { "inTangents", k.inTangents }, { "outTangents", k.outTangents }, { "tangentMode", k.tangentMode },
        });
    }
    var dict = new System.Collections.Generic.Dictionary<string, object>
    {
        { "success", r.success }, { "clipPath", r.clipPath }, { "targetPath", r.targetPath },
        { "typeName", r.typeName }, { "propertyName", r.propertyName },
        { "channels", r.channels }, { "keyframes", keyframes },
    };
    if (r.error != null) dict["error"] = r.error;
    return dict;
}
"""


def _to_dictionary_event_edit_result_code() -> str:
    return """
System.Collections.Generic.Dictionary<string, object> ToDictionary(AnimationEventEditResult r)
{
    var dict = new System.Collections.Generic.Dictionary<string, object>
    {
        { "success", r.success }, { "clipPath", r.clipPath }, { "hasTime", r.hasTime },
        { "functionName", r.functionName }, { "eventsAffected", r.eventsAffected },
        { "backupId", r.backupId }, { "undoGroupId", r.undoGroupId }, { "warnings", r.warnings },
    };
    if (r.hasTime) dict["time"] = r.time;
    if (r.error != null) dict["error"] = r.error;
    return dict;
}
"""


def _to_dictionary_list_backups_result_code() -> str:
    return """
System.Collections.Generic.Dictionary<string, object> ToDictionary(ListAnimationBackupsResult r)
{
    var backups = new System.Collections.Generic.List<object>();
    foreach (var b in r.backups)
    {
        backups.Add(new System.Collections.Generic.Dictionary<string, object>
        {
            { "backupId", b.backupId }, { "clipPath", b.clipPath },
            { "createdAt", b.createdAt }, { "operation", b.operation }, { "sizeBytes", b.sizeBytes },
        });
    }
    var dict = new System.Collections.Generic.Dictionary<string, object>
    {
        { "success", r.success }, { "clipPath", r.clipPath }, { "backups", backups },
    };
    if (r.error != null) dict["error"] = r.error;
    return dict;
}
"""


def _to_dictionary_restore_backup_result_code() -> str:
    return """
System.Collections.Generic.Dictionary<string, object> ToDictionary(RestoreAnimationClipResult r)
{
    var dict = new System.Collections.Generic.Dictionary<string, object>
    {
        { "success", r.success }, { "clipPath", r.clipPath },
        { "restoredFromBackupId", r.restoredFromBackupId }, { "preRestoreBackupId", r.preRestoreBackupId },
        { "warnings", r.warnings },
    };
    if (r.error != null) dict["error"] = r.error;
    return dict;
}
"""


def _list_keyframes_code(
    *,
    clip_path: str,
    target_path: str,
    type_name: str,
    property_name: str,
) -> str:
    body = extract_as_local_function(_AUTHORING_CS, "ListKeyframes")
    return f"""
{_preamble(*_KEYFRAME_PRIMITIVES)}
{_to_dictionary_list_keyframes_result_code()}
{body}
var result = ListKeyframes({_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)});
return ToDictionary(result);
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
    body = extract_as_local_function(_AUTHORING_CS, "SetKeyframe")
    return f"""
{_preamble(*_KEYFRAME_PRIMITIVES)}
{_to_dictionary_clip_edit_result_code()}
{body}
var result = SetKeyframe(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {time}f, {_float_array_lit(values)}, {_lit(tangent_mode)},
    {_float_array_lit(in_tangent)}, {_float_array_lit(out_tangent)}, {_lit(operation_id)});
return ToDictionary(result);
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
    body = extract_as_local_function(_AUTHORING_CS, "MoveKeyframe")
    return f"""
{_preamble(*_KEYFRAME_PRIMITIVES)}
{_to_dictionary_clip_edit_result_code()}
{body}
var result = MoveKeyframe(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {from_time}f, {to_time}f, {_lit(operation_id)});
return ToDictionary(result);
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
    body = extract_as_local_function(_AUTHORING_CS, "RemoveKeyframe")
    return f"""
{_preamble(*_KEYFRAME_PRIMITIVES)}
{_to_dictionary_clip_edit_result_code()}
{body}
var result = RemoveKeyframe(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {time}f, {_lit(operation_id)});
return ToDictionary(result);
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
    body = extract_as_local_function(_AUTHORING_CS, "SetKeyframeHold")
    return f"""
{_preamble(*_KEYFRAME_PRIMITIVES)}
{_to_dictionary_clip_edit_result_code()}
{body}
var result = SetKeyframeHold(
    {_lit(clip_path)}, {_lit(target_path)}, {_lit(type_name)}, {_lit(property_name)},
    {time}f, {hold_until}f, {_float_array_lit(value)}, {_bool_lit(value is not None)}, {_lit(operation_id)});
return ToDictionary(result);
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
    body = extract_as_local_function(_AUTHORING_CS, "CreateEvent")
    return f"""
{_preamble(*_EVENT_PRIMITIVES)}
{_to_dictionary_event_edit_result_code()}
{body}
var result = CreateEvent(
    {_lit(clip_path)}, {time}f, {_lit(function_name)}, {_lit(string_param)},
    {float_param}f, {int_param}, {_lit(operation_id)});
return ToDictionary(result);
"""


def _remove_event_code(
    *,
    clip_path: str,
    time: float,
    function_name: str | None,
    operation_id: str,
) -> str:
    body = extract_as_local_function(_AUTHORING_CS, "RemoveEvent")
    return f"""
{_preamble(*_EVENT_PRIMITIVES)}
{_to_dictionary_event_edit_result_code()}
{body}
var result = RemoveEvent({_lit(clip_path)}, {time}f, {_lit(function_name)}, {_lit(operation_id)});
return ToDictionary(result);
"""


def _list_backups_code(*, clip_path: str) -> str:
    body = extract_as_local_function(_BACKUP_CS, "ListBackups")
    return f"""
{_preamble(*_BACKUP_PRIMITIVES)}
{_to_dictionary_list_backups_result_code()}
{body}
var result = ListBackups({_lit(clip_path)});
return ToDictionary(result);
"""


def _restore_backup_code(*, clip_path: str, backup_id: str, operation_id: str) -> str:
    body = extract_as_local_function(_BACKUP_CS, "RestoreBackup")
    return f"""
{_preamble(*_BACKUP_PRIMITIVES)}
{_to_dictionary_restore_backup_result_code()}
{body}
var clip = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.AnimationClip>({_lit(clip_path)});
if (clip == null)
{{
    return new System.Collections.Generic.Dictionary<string, object> {{
        {{ "success", false }}, {{ "clipPath", {_lit(clip_path)} }},
        {{ "error", "AnimationClip not found at exact path " + {_lit(clip_path)} }},
    }};
}}
var result = RestoreBackup(clip, {_lit(clip_path)}, {_lit(backup_id)}, {_lit(operation_id)});
return ToDictionary(result);
"""
