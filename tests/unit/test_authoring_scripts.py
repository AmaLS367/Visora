from backend.tools.animation.authoring_scripts import (
    _create_event_code,
    _hold_keyframe_code,
    _list_backups_code,
    _list_keyframes_code,
    _move_keyframe_code,
    _remove_event_code,
    _remove_keyframe_code,
    _restore_backup_code,
    _set_keyframe_code,
)


def test_set_keyframe_code_is_fully_self_contained() -> None:
    code = _set_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        values=[1.0, 2.0, 3.0],
        tangent_mode="smooth",
        in_tangent=None,
        out_tangent=None,
        operation_id="op-1",
    )
    assert "Visora.Editor.Services" not in code  # no reference to the compiled assembly at all
    assert "using System;" not in code and "using UnityEditor;" not in code  # statement body only
    assert "public static" not in code and "private static" not in code  # no member declarations
    assert '"Assets/A.anim"' in code
    assert "0.5f" in code
    assert "ResolveComponentType(" in code and "ResolveChannels(" in code  # the algorithm is present, not referenced


def test_create_event_code_escapes_string_param() -> None:
    code = _create_event_code(
        clip_path="Assets/A.anim",
        time=0.2,
        function_name="OnHit",
        string_param='say "hi"',
        float_param=1.0,
        int_param=0,
        operation_id="op-2",
    )
    assert '\\"hi\\"' in code
    assert "Visora.Editor.Services" not in code


def test_remove_event_code_passes_null_for_wildcard_function_name() -> None:
    code = _remove_event_code(clip_path="Assets/A.anim", time=0.2, function_name=None, operation_id="op-3")
    assert "null" in code
    assert "Visora.Editor.Services" not in code


def test_remove_keyframe_code_is_self_contained() -> None:
    code = _remove_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        operation_id="op-4",
    )
    assert "Visora.Editor.Services" not in code
    assert "FindKeyIndexNearTime(" in code


def test_move_keyframe_code_is_self_contained() -> None:
    code = _move_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        from_time=0.5,
        to_time=1.0,
        operation_id="op-move",
    )
    assert "Visora.Editor.Services" not in code
    assert "MoveKeyframe(" in code


def test_hold_keyframe_code_is_self_contained() -> None:
    code = _hold_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        hold_until=1.5,
        value=[1.0, 2.0, 3.0],
        operation_id="op-hold",
    )
    assert "Visora.Editor.Services" not in code
    assert "SetKeyframeHold(" in code


def test_list_keyframes_code_is_self_contained() -> None:
    code = _list_keyframes_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
    )
    assert "Visora.Editor.Services" not in code
    assert "ListKeyframes(" in code


def test_list_backups_and_restore_code_are_self_contained() -> None:
    list_code = _list_backups_code(clip_path="Assets/A.anim")
    restore_code = _restore_backup_code(clip_path="Assets/A.anim", backup_id="x/y.anim", operation_id="op-5")
    assert "Visora.Editor.Services" not in list_code
    assert "Visora.Editor.Services" not in restore_code
