from pathlib import Path

import pytest
from mcp.server.mcpserver import Image
from PIL import Image as PILImage

from backend.schemas.animation import AnimationPreviewKeyFrame, AnimationPreviewMotionSummary
from backend.schemas.preview_record import (
    AnimationPreviewComparisonResult,
    AnimationPreviewRecord,
    PreviewActionMarker,
    PreviewArtifactFiles,
    PreviewCameraInfo,
    PreviewCaptureSettings,
    PreviewClipInfo,
    PreviewEditorState,
    PreviewSceneInfo,
)
from backend.tools.animation.preview_compare import compare_records
from backend.tools.animation.preview_store import get_preview_record, save_preview_record
from backend.tools.animation.qa import compare_animation_previews


def _make_record(  # noqa: PLR0913
    preview_id: str,
    clip_path: str = "Assets/Punch.anim",
    clip_name: str = "Punch",
    clip_length: float = 1.0,
    camera_name: str = "Main Camera",
    framing: str = "visible",
    auto_frame_status: str = "not_needed",
    actual_fps: float = 24.0,
    width: int = 640,
    height: int = 360,
    is_static: bool = False,
    peak_timestamp: float = 0.5,
    peak_ratio: float = 0.30,
    mean_ratio: float = 0.10,
    pose_restored: bool = True,
    markers: list[PreviewActionMarker] | None = None,
    contact_sheet_path: str | None = None,
) -> AnimationPreviewRecord:
    return AnimationPreviewRecord(
        preview_id=preview_id,
        created_at="2026-09-10T12:00:00Z",
        target_object_path="Characters/Hero",
        scene=PreviewSceneInfo(scene_path="Assets/Scene.unity", scene_name="Scene", is_dirty=False),
        clip=PreviewClipInfo(
            clip_path=clip_path,
            clip_name=clip_name,
            length=clip_length,
            loop_time=False,
            event_count=len(markers or []),
        ),
        camera=PreviewCameraInfo(
            requested_camera_name=camera_name,
            rendered_camera_name=camera_name,
            auto_frame_status=auto_frame_status,
            framing_status_before=framing,
        ),
        capture_settings=PreviewCaptureSettings(
            requested_start_time=0.0,
            requested_end_time=clip_length,
            requested_fps=int(actual_fps),
            effective_fps=actual_fps,
            actual_fps=actual_fps,
            width=width,
            height=height,
            frame_count=int(clip_length * actual_fps),
        ),
        editor_state=PreviewEditorState(pose_restored=pose_restored),
        action_markers=markers or [],
        artifacts=PreviewArtifactFiles(
            record_path="",
            mp4_path="/path/preview.mp4",
            contact_sheet_path=contact_sheet_path,
        ),
        motion_summary=AnimationPreviewMotionSummary(
            peak_motion_timestamp=peak_timestamp,
            peak_changed_pixel_ratio=peak_ratio,
            mean_changed_pixel_ratio=mean_ratio,
            is_static=is_static,
        ),
        motion_timeline=[0.1, peak_ratio, 0.05],
        key_frames=[
            AnimationPreviewKeyFrame(
                frame_index=1,
                timestamp_seconds=peak_timestamp,
                normalized_time=0.5,
                source="peak_motion",
                file_path="/path/frame.png",
                width=width,
                height=height,
            )
        ],
    )


def test_compare_identical_records() -> None:
    rec1 = _make_record("prev_1")
    rec2 = _make_record("prev_2")

    result, _diff_img = compare_records(rec1, rec2)
    assert result.success is True
    assert result.baseline_preview_id == "prev_1"
    assert result.comparison_preview_id == "prev_2"
    assert result.inputs_diff is not None
    assert result.inputs_diff.clip_path_changed is False
    assert result.inputs_diff.camera_changed is False
    assert result.motion_diff is not None
    assert result.motion_diff.peak_motion_timestamp_delta == 0.0
    assert len(result.regression_warnings) == 0
    assert "No significant divergence" in result.summary


def test_compare_detects_inputs_and_motion_changes() -> None:
    rec1 = _make_record("prev_1", clip_length=1.0, peak_timestamp=0.4, peak_ratio=0.20)
    rec2 = _make_record("prev_2", clip_length=1.2, peak_timestamp=0.55, peak_ratio=0.35)

    result, _ = compare_records(rec1, rec2)
    assert result.success is True
    assert result.inputs_diff is not None
    assert result.inputs_diff.clip_length_delta == 0.2
    assert result.motion_diff is not None
    assert result.motion_diff.peak_motion_timestamp_delta == 0.15
    assert result.motion_diff.peak_changed_pixel_ratio_delta == 0.15
    assert "Peak motion shifted by +0.15s." in result.summary


def test_compare_detects_action_marker_changes() -> None:
    rec1 = _make_record(
        "prev_1",
        markers=[
            PreviewActionMarker(time=0.4, label="HitImpact"),
            PreviewActionMarker(time=0.8, label="FollowThrough"),
        ],
    )
    rec2 = _make_record(
        "prev_2",
        markers=[
            PreviewActionMarker(time=0.45, label="HitImpact"),
            PreviewActionMarker(time=0.9, label="NewEvent"),
        ],
    )

    result, _ = compare_records(rec1, rec2)
    assert len(result.events_diff) == 3
    assert any("Shifted marker 'HitImpact' by +0.05s" in e for e in result.events_diff)
    assert any("Added marker 'NewEvent'" in e for e in result.events_diff)
    assert any("Removed marker 'FollowThrough'" in e for e in result.events_diff)


def test_compare_flags_motion_loss_and_framing_regressions() -> None:
    rec1 = _make_record("prev_1", is_static=False, framing="visible", pose_restored=True)
    rec2 = _make_record("prev_2", is_static=True, framing="clipped", pose_restored=False)

    result, _ = compare_records(rec1, rec2)
    assert len(result.regression_warnings) == 3
    assert any("evaluated as static" in r for r in result.regression_warnings)
    assert any("Camera framing degraded to 'clipped'" in r for r in result.regression_warnings)
    assert any("target pose was not restored" in r for r in result.regression_warnings)


def test_compare_generates_side_by_side_contact_sheet(tmp_path: Path) -> None:
    # Create two dummy images for contact sheets
    sheet1_path = tmp_path / "sheet1.png"
    sheet2_path = tmp_path / "sheet2.png"
    PILImage.new("RGB", (320, 180), color=(255, 0, 0)).save(sheet1_path)
    PILImage.new("RGB", (320, 180), color=(0, 255, 0)).save(sheet2_path)

    rec1 = _make_record("prev_img_1", contact_sheet_path=str(sheet1_path))
    rec2 = _make_record("prev_img_2", contact_sheet_path=str(sheet2_path))

    result, diff_img = compare_records(rec1, rec2)
    assert diff_img is not None
    assert diff_img.is_file()
    assert result.visual_comparison_sheet_path == str(diff_img)


@pytest.mark.anyio
async def test_compare_animation_previews_loads_from_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point preview store to tmp_path
    monkeypatch.setattr("backend.tools.animation.qa.get_preview_record", lambda pid: get_rec_from_tmp(pid, tmp_path))

    rec1 = _make_record("prev_store_1", peak_ratio=0.15)
    rec2 = _make_record("prev_store_2", peak_ratio=0.35)
    save_preview_record(rec1, base_dir=tmp_path)
    save_preview_record(rec2, base_dir=tmp_path)

    def get_rec_from_tmp(pid: str, base: Path) -> AnimationPreviewRecord | None:
        return get_preview_record(pid, base_dir=base)

    res = await compare_animation_previews(
        baseline_preview_id="prev_store_1",
        comparison_preview_id="prev_store_2",
        baseline_slide_distance=0.10,
        comparison_slide_distance=0.02,
    )
    # Since no contact sheets were saved on disk in this test, returns AnimationPreviewComparisonResult directly
    assert isinstance(res, AnimationPreviewComparisonResult)
    assert res.success is True
    assert res.sliding_reduced_percent == 80.0
    assert res.motion_diff is not None
    assert res.motion_diff.peak_changed_pixel_ratio_delta == 0.20
