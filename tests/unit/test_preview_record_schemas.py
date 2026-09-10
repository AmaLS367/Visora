from backend.schemas.animation import (
    AnimationPreviewKeyFrame,
    AnimationPreviewMotionSummary,
)
from backend.schemas.preview_record import (
    AnimationPreviewComparisonResult,
    AnimationPreviewInputsDiff,
    AnimationPreviewListResult,
    AnimationPreviewMotionDiff,
    AnimationPreviewRecord,
    AnimationPreviewRecordResult,
    AnimationPreviewRecordSummary,
    PreviewActionMarker,
    PreviewArtifactFiles,
    PreviewCameraInfo,
    PreviewCaptureSettings,
    PreviewClipInfo,
    PreviewEditorState,
    PreviewSceneInfo,
)


def _sample_record() -> AnimationPreviewRecord:
    return AnimationPreviewRecord(
        preview_id="prev_20260910_110000_12345678",
        created_at="2026-09-10T11:00:00Z",
        target_object_path="Characters/Hero",
        scene=PreviewSceneInfo(
            scene_path="Assets/Scenes/TestScene.unity",
            scene_name="TestScene",
            is_dirty=False,
        ),
        clip=PreviewClipInfo(
            clip_path="Assets/Animations/HeroAttack.anim",
            clip_name="HeroAttack",
            length=1.5,
            loop_time=False,
            event_count=1,
            dangerous_curves=[],
        ),
        camera=PreviewCameraInfo(
            requested_camera_name="Main Camera",
            rendered_camera_name="Main Camera",
            auto_frame_status="not_needed",
            framing_status_before="visible",
        ),
        capture_settings=PreviewCaptureSettings(
            requested_start_time=0.0,
            requested_end_time=1.5,
            requested_fps=24,
            effective_fps=24.0,
            actual_fps=24.0,
            width=640,
            height=360,
            frame_ceiling_applied=False,
            range_truncated=False,
            timing_source="edit_mode_sampled",
            frame_count=36,
        ),
        editor_state=PreviewEditorState(
            is_playing=False,
            is_paused=False,
            pose_restored=True,
            scene_dirtied_by_preview=False,
            preview_camera_created=False,
            preview_camera_destroyed=None,
        ),
        action_markers=[
            PreviewActionMarker(time=0.5, label="HitImpact", marker_type="event"),
            PreviewActionMarker(time=0.5, label="PeakMotion", marker_type="peak_motion"),
        ],
        artifacts=PreviewArtifactFiles(
            record_path="/artifacts/animation_previews/prev_20260910_110000_12345678/record.json",
            mp4_path="/artifacts/animation_previews/prev_20260910_110000_12345678/preview.mp4",
            contact_sheet_path="/artifacts/animation_previews/prev_20260910_110000_12345678/contact_sheet.png",
            key_frame_paths=["/artifacts/animation_previews/prev_20260910_110000_12345678/keyframe_0.png"],
        ),
        motion_summary=AnimationPreviewMotionSummary(
            peak_motion_timestamp=0.5,
            peak_changed_pixel_ratio=0.35,
            mean_changed_pixel_ratio=0.10,
            static_intervals=[],
            is_static=False,
        ),
        motion_timeline=[0.05, 0.12, 0.35, 0.20],
        key_frames=[
            AnimationPreviewKeyFrame(
                frame_index=12,
                timestamp_seconds=0.5,
                normalized_time=0.33,
                source="peak_motion",
                event_functions=["HitImpact"],
                file_path="/artifacts/animation_previews/prev_20260910_110000_12345678/keyframe_0.png",
                width=640,
                height=360,
                changed_pixel_ratio_from_previous=0.35,
            )
        ],
        warnings=[],
        recommended_interpretation="Review key frames in timestamp order.",
    )


def test_animation_preview_record_serialization() -> None:
    record = _sample_record()
    data = record.model_dump()
    assert data["preview_id"] == "prev_20260910_110000_12345678"
    assert data["clip"]["clip_name"] == "HeroAttack"
    assert data["camera"]["auto_frame_status"] == "not_needed"
    assert len(data["action_markers"]) == 2

    # Round-trip through JSON
    json_str = record.model_dump_json()
    reconstructed = AnimationPreviewRecord.model_validate_json(json_str)
    assert reconstructed.preview_id == record.preview_id
    assert reconstructed.artifacts.mp4_path == record.artifacts.mp4_path
    assert reconstructed.motion_summary is not None
    assert reconstructed.motion_summary.peak_motion_timestamp == 0.5


def test_animation_preview_record_summary() -> None:
    summary = AnimationPreviewRecordSummary(
        preview_id="prev_123",
        created_at="2026-09-10T11:00:00Z",
        target_object_path="Hero",
        clip_path="Assets/Hero.anim",
        clip_name="Hero",
        camera_name="Main Camera",
        frame_count=24,
        duration=1.0,
        is_static=False,
        mp4_path="/path/to/video.mp4",
        record_path="/path/to/record.json",
    )
    assert summary.preview_id == "prev_123"
    assert summary.duration == 1.0


def test_animation_preview_record_result() -> None:
    rec = _sample_record()
    res = AnimationPreviewRecordResult(success=True, record=rec)
    assert res.success is True
    assert res.record is not None
    assert res.record.preview_id == rec.preview_id

    fail_res = AnimationPreviewRecordResult(success=False, error="Record not found")
    assert fail_res.success is False
    assert fail_res.record is None


def test_animation_preview_list_result() -> None:
    res = AnimationPreviewListResult(
        success=True,
        records=[
            AnimationPreviewRecordSummary(
                preview_id="prev_1",
                created_at="2026-09-10T11:00:00Z",
                target_object_path="Hero",
                clip_path="Assets/Hero.anim",
                clip_name="Hero",
                camera_name="Main Camera",
                frame_count=10,
                duration=0.5,
                is_static=False,
                mp4_path=None,
                record_path="/path/1.json",
            )
        ],
        total_count=1,
    )
    assert res.success is True
    assert len(res.records) == 1
    assert res.total_count == 1


def test_animation_preview_comparison_result() -> None:
    comp = AnimationPreviewComparisonResult(
        success=True,
        baseline_preview_id="prev_1",
        comparison_preview_id="prev_2",
        summary="Improved motion smoothness by 40%.",
        inputs_diff=AnimationPreviewInputsDiff(
            clip_path_changed=False,
            baseline_clip_path="Assets/Hero.anim",
            comparison_clip_path="Assets/Hero.anim",
            clip_length_delta=0.0,
            camera_changed=False,
            baseline_camera="Main Camera",
            comparison_camera="Main Camera",
            fps_delta=0.0,
            resolution_changed=False,
        ),
        motion_diff=AnimationPreviewMotionDiff(
            peak_motion_timestamp_delta=0.1,
            peak_changed_pixel_ratio_delta=0.05,
            mean_changed_pixel_ratio_delta=0.02,
            static_status_changed=False,
            is_now_static=False,
            was_static=False,
        ),
        visual_comparison_sheet_path="/path/to/diff.png",
        events_diff=["Event 'Hit' moved by +0.10s"],
        sliding_reduced_percent=50.0,
        jerk_reduced_percent=40.0,
        improvements=["Motion peak aligned with Hit event."],
        regression_warnings=[],
    )
    assert comp.success is True
    assert comp.sliding_reduced_percent == 50.0
    assert comp.inputs_diff is not None
    assert comp.inputs_diff.clip_path_changed is False
    assert comp.motion_diff is not None
    assert comp.motion_diff.peak_motion_timestamp_delta == 0.1
