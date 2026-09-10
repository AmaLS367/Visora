from backend.schemas import (
    AnimationBackupInfo,
    AnimationKeyframeInfo,
    ListAnimationBackupsResult,
    ListAnimationKeyframesResult,
    RestoreAnimationClipResult,
)


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
        backup_id="Assets__A.anim/20260905-090000-edit_animation_transaction.anim",
        clip_path="Assets/A.anim",
        created_at="2026-09-05T09:00:00Z",
        operation="edit_animation_transaction",
        size_bytes=1024,
    )
    listed = ListAnimationBackupsResult(success=True, clip_path="Assets/A.anim", backups=[info])
    restored = RestoreAnimationClipResult(
        success=True,
        clip_path="Assets/A.anim",
        restored_from_backup_id=info.backup_id,
        pre_restore_backup_id="Assets__A.anim/20260905-091500-restore_animation_clip.anim",
    )
    assert listed.backups[0].operation == "edit_animation_transaction"
    assert restored.pre_restore_backup_id is not None
