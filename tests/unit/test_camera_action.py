from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas.camera_action import CameraSubjectContactResult
from backend.tools.animation.camera_action import solve_camera_subject_contact


def test_camera_subject_contact_schema() -> None:
    res = CameraSubjectContactResult(
        success=True,
        character_backup_id="char-b1",
        camera_backup_id="cam-b1",
        impact_world_position=[0.0, 1.2, 0.5],
        impact_screen_residual_pixels=[1.2, 0.8],
        max_limb_reach_ratio=0.88,
        keyframes_modified_count=20,
    )
    assert res.success is True
    assert res.max_limb_reach_ratio == 0.88
    assert res.impact_screen_residual_pixels == [1.2, 0.8]


@pytest.mark.anyio
async def test_solve_camera_subject_contact_tool() -> None:
    mock_response: dict[str, Any] = {
        "success": True,
        "characterBackupId": "char-backup-dropkick",
        "cameraBackupId": "cam-backup-recoil",
        "impactWorldPosition": [0.1, 1.3, -0.4],
        "impactScreenResidualPixels": [2.1, 1.5],
        "maxLimbReachRatio": 0.91,
        "keyframesModifiedCount": 24,
        "warnings": [],
    }

    with patch(
        "backend.bridge.client.UnityBridge.solve_camera_subject_contact_native",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await solve_camera_subject_contact(
            character_path="Characters/Hero",
            character_clip_path="Assets/Animations/Hero_Dropkick.anim",
            camera_name="Main Camera",
            camera_clip_path="Assets/Animations/Camera_Action.anim",
            effector="right_foot",
            impact_time=0.6,
            contact_duration=0.2,
            lens_viewport=[0.5, 0.5],
            lens_distance_meters=0.25,
            hit_stop_duration=0.08,
            camera_recoil_impulse=[0.0, -0.2, -0.5],
        )

    assert result.success is True
    assert result.character_backup_id == "char-backup-dropkick"
    assert result.camera_backup_id == "cam-backup-recoil"
    assert result.max_limb_reach_ratio == 0.91
    assert result.keyframes_modified_count == 24
