from pathlib import Path

import pytest

from backend.schemas.animation import AnimationPreviewKeyFrame, AnimationPreviewMotionSummary
from backend.schemas.preview_record import (
    AnimationPreviewListResult,
    AnimationPreviewRecord,
    AnimationPreviewRecordResult,
    PreviewActionMarker,
    PreviewArtifactFiles,
    PreviewCameraInfo,
    PreviewCaptureSettings,
    PreviewClipInfo,
    PreviewEditorState,
    PreviewSceneInfo,
)
from backend.tools.animation.preview_store import (
    get_preview_record,
    list_preview_records,
    save_preview_record,
)
from backend.tools.animation.records import (
    get_animation_preview_record,
    list_animation_preview_records,
)


def _make_record(preview_id: str, clip_path: str = "Assets/Test.anim") -> AnimationPreviewRecord:
    return AnimationPreviewRecord(
        preview_id=preview_id,
        created_at="2026-09-10T12:00:00Z",
        target_object_path="Characters/Hero",
        scene=PreviewSceneInfo(scene_path="Assets/Scene.unity", scene_name="Scene", is_dirty=False),
        clip=PreviewClipInfo(clip_path=clip_path, clip_name="Test", length=1.0, loop_time=False),
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


@pytest.mark.anyio
async def test_get_animation_preview_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _make_record("prev_tool_test")
    save_preview_record(rec, base_dir=tmp_path)

    # Monkeypatch get_preview_record in records module to use tmp_path
    monkeypatch.setattr(
        "backend.tools.animation.records.get_preview_record",
        lambda pid: get_preview_record(pid, base_dir=tmp_path),
    )

    # Success case
    res = await get_animation_preview_record("prev_tool_test")
    assert isinstance(res, AnimationPreviewRecordResult)
    assert res.success is True
    assert res.record is not None
    assert res.record.preview_id == "prev_tool_test"

    # Missing record case
    missing_res = await get_animation_preview_record("prev_does_not_exist")
    assert isinstance(missing_res, AnimationPreviewRecordResult)
    assert missing_res.success is False
    assert "not found" in (missing_res.error or "").lower()


@pytest.mark.anyio
async def test_list_animation_preview_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec1 = _make_record("prev_list_1", clip_path="Assets/Punch.anim")
    rec2 = _make_record("prev_list_2", clip_path="Assets/Kick.anim")
    save_preview_record(rec1, base_dir=tmp_path)
    save_preview_record(rec2, base_dir=tmp_path)

    monkeypatch.setattr(
        "backend.tools.animation.records.list_preview_records",
        lambda clip_path=None, target_object_path=None, limit=10: list_preview_records(
            clip_path=clip_path,
            target_object_path=target_object_path,
            limit=limit,
            base_dir=tmp_path,
        ),
    )

    res = await list_animation_preview_records()
    assert isinstance(res, AnimationPreviewListResult)
    assert res.success is True
    assert res.total_count == 2
    assert len(res.records) == 2

    # Filter by clip
    kick_res = await list_animation_preview_records(clip_path="Kick")
    assert kick_res.success is True
    assert kick_res.total_count == 1
    assert kick_res.records[0].preview_id == "prev_list_2"
