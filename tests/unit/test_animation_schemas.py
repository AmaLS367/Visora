from backend.schemas import (
    AnimationBackupInfo,
    AnimationClipEditResult,
    AnimationEventEditResult,
    AnimationKeyframeInfo,
    ListAnimationBackupsResult,
    ListAnimationKeyframesResult,
    RestoreAnimationClipResult,
)


def test_animation_clip_edit_result_defaults() -> None:
    result = AnimationClipEditResult(success=True)
    assert result.channels_affected == []
    assert result.curve_created is False
    assert result.keys_cleared == []
    assert result.warnings == []


def test_list_animation_keyframes_result_round_trip() -> None:
    keyframe = AnimationKeyframeInfo(
        time=0.5,
        values=[1.0, 2.0, 3.0],
        in_tangents=[0.0, 0.0, 0.0],
        out_tangents=[0.0, 0.0, 0.0],
        tangent_mode="smooth",
    )
    result = ListAnimationKeyframesResult(
        success=True,
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        channels=["m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z"],
        keyframes=[keyframe],
    )
    assert result.keyframes[0].values == [1.0, 2.0, 3.0]


def test_backup_schemas_round_trip() -> None:
    info = AnimationBackupInfo(
        backup_id="Assets__A.anim/20260905-090000-set_animation_keyframe.anim",
        clip_path="Assets/A.anim",
        created_at="2026-09-05T09:00:00Z",
        operation="set_animation_keyframe",
        size_bytes=1024,
    )
    listed = ListAnimationBackupsResult(success=True, clip_path="Assets/A.anim", backups=[info])
    restored = RestoreAnimationClipResult(
        success=True,
        clip_path="Assets/A.anim",
        restored_from_backup_id=info.backup_id,
        pre_restore_backup_id="Assets__A.anim/20260905-091500-restore_animation_clip.anim",
    )
    assert listed.backups[0].operation == "set_animation_keyframe"
    assert restored.pre_restore_backup_id is not None


def test_event_edit_result_defaults() -> None:
    result = AnimationEventEditResult(success=True, events_affected=2)
    assert result.events_affected == 2
    assert result.warnings == []
