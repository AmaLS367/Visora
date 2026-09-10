import time
from pathlib import Path

from backend.schemas.animation import AnimationPreviewKeyFrame, AnimationPreviewMotionSummary
from backend.schemas.preview_record import (
    AnimationPreviewRecord,
    PreviewActionMarker,
    PreviewArtifactFiles,
    PreviewCameraInfo,
    PreviewCaptureSettings,
    PreviewClipInfo,
    PreviewEditorState,
    PreviewSceneInfo,
)
from backend.tools.animation.preview_store import (
    generate_preview_id,
    get_preview_dir,
    get_preview_record,
    list_preview_records,
    prune_preview_records,
    save_preview_record,
)


def _make_dummy_record(
    preview_id: str,
    created_at: str,
    clip_path: str = "Assets/Hero.anim",
    target_object_path: str = "Hero",
) -> AnimationPreviewRecord:
    return AnimationPreviewRecord(
        preview_id=preview_id,
        created_at=created_at,
        target_object_path=target_object_path,
        scene=PreviewSceneInfo(scene_path="Assets/Scene.unity", scene_name="Scene", is_dirty=False),
        clip=PreviewClipInfo(clip_path=clip_path, clip_name="Hero", length=1.0, loop_time=False),
        camera=PreviewCameraInfo(
            requested_camera_name="Main Camera",
            rendered_camera_name="Main Camera",
            auto_frame_status="not_needed",
        ),
        capture_settings=PreviewCaptureSettings(
            requested_start_time=0.0,
            requested_end_time=1.0,
            requested_fps=24,
            effective_fps=24.0,
            actual_fps=24.0,
            width=640,
            height=360,
            frame_count=24,
        ),
        editor_state=PreviewEditorState(),
        action_markers=[PreviewActionMarker(time=0.5, label="Strike")],
        artifacts=PreviewArtifactFiles(record_path="", mp4_path="/path/video.mp4"),
        motion_summary=AnimationPreviewMotionSummary(peak_motion_timestamp=0.5, is_static=False),
        motion_timeline=[0.1, 0.2],
        key_frames=[
            AnimationPreviewKeyFrame(
                frame_index=1,
                timestamp_seconds=0.5,
                normalized_time=0.5,
                source="peak_motion",
                file_path="/path/frame.png",
                width=640,
                height=360,
            )
        ],
    )


def test_generate_preview_id() -> None:
    id1 = generate_preview_id()
    id2 = generate_preview_id()
    assert id1.startswith("prev_")
    assert id2.startswith("prev_")
    assert id1 != id2


def test_save_and_get_preview_record(tmp_path: Path) -> None:
    rec = _make_dummy_record("prev_test_1", "2026-09-10T12:00:00Z")
    saved_path = save_preview_record(rec, base_dir=tmp_path)
    assert saved_path.is_file()
    assert saved_path.name == "record.json"
    assert "prev_test_1" in str(saved_path)

    loaded = get_preview_record("prev_test_1", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.preview_id == "prev_test_1"
    assert loaded.clip.clip_path == "Assets/Hero.anim"
    assert loaded.artifacts.record_path == str(saved_path.resolve())

    # Non-existent record
    assert get_preview_record("non_existent_id", base_dir=tmp_path) is None


def test_list_preview_records(tmp_path: Path) -> None:
    rec1 = _make_dummy_record(
        "prev_1", "2026-09-10T10:00:00Z", clip_path="Assets/Punch.anim", target_object_path="Player"
    )
    rec2 = _make_dummy_record(
        "prev_2", "2026-09-10T12:00:00Z", clip_path="Assets/Kick.anim", target_object_path="Enemy"
    )
    rec3 = _make_dummy_record(
        "prev_3", "2026-09-10T11:00:00Z", clip_path="Assets/Kick.anim", target_object_path="Player"
    )

    save_preview_record(rec1, base_dir=tmp_path)
    save_preview_record(rec2, base_dir=tmp_path)
    save_preview_record(rec3, base_dir=tmp_path)

    # All records, sorted descending by created_at
    all_recs = list_preview_records(base_dir=tmp_path)
    assert len(all_recs) == 3
    assert [r.preview_id for r in all_recs] == ["prev_2", "prev_3", "prev_1"]

    # Filter by clip_path
    kick_recs = list_preview_records(clip_path="Kick", base_dir=tmp_path)
    assert len(kick_recs) == 2
    assert [r.preview_id for r in kick_recs] == ["prev_2", "prev_3"]

    # Filter by target_object_path
    player_recs = list_preview_records(target_object_path="Player", base_dir=tmp_path)
    assert len(player_recs) == 2
    assert [r.preview_id for r in player_recs] == ["prev_3", "prev_1"]

    # Limit
    limited = list_preview_records(limit=1, base_dir=tmp_path)
    assert len(limited) == 1
    assert limited[0].preview_id == "prev_2"


def test_prune_preview_records(tmp_path: Path) -> None:
    # Create 4 preview records with slight delays to have distinct mtime
    for i in range(4):
        p_id = f"prev_prune_{i}"
        rec = _make_dummy_record(p_id, f"2026-09-10T10:0{i}:00Z")
        save_preview_record(rec, base_dir=tmp_path)
        time.sleep(0.01)

    pruned = prune_preview_records(max_count=2, base_dir=tmp_path)
    assert pruned == 2

    remaining = list_preview_records(base_dir=tmp_path)
    assert len(remaining) == 2
