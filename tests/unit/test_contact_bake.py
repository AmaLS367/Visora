from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas.contact_bake import BakeEffectorContactResult
from backend.tools.animation.contact_bake import bake_effector_contact


def test_contact_bake_schema() -> None:
    res = BakeEffectorContactResult(
        success=True,
        clip_path="Assets/Animations/Walk.anim",
        effector="left_foot",
        backup_id="backup-123",
        keyframes_modified_count=16,
        max_effector_displacement=0.045,
        residual_error=0.002,
        active_duration=0.8,
    )
    assert res.success is True
    assert res.effector == "left_foot"
    assert res.keyframes_modified_count == 16
    assert res.max_effector_displacement == 0.045


@pytest.mark.anyio
async def test_bake_effector_contact_world_point() -> None:
    mock_response: dict[str, Any] = {
        "success": True,
        "clipPath": "Assets/Animations/Kick.anim",
        "effector": "right_foot",
        "backupId": "backup-kick-1",
        "keyframesModifiedCount": 24,
        "maxEffectorDisplacement": 0.12,
        "residualError": 0.001,
        "activeDuration": 0.5,
        "warnings": [],
    }

    with patch(
        "backend.bridge.client.UnityBridge.bake_effector_contact_native",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await bake_effector_contact(
            clip_path="Assets/Animations/Kick.anim",
            target_object_path="Characters/Fighter",
            effector="right_foot",
            target_type="world_point",
            target_position=[0.0, 0.0, 1.2],
            time_range=[0.3, 0.6],
            blend_in_seconds=0.1,
            blend_out_seconds=0.1,
        )

    assert result.success is True
    assert result.effector == "right_foot"
    assert result.backup_id == "backup-kick-1"
    assert result.keyframes_modified_count == 24
    assert result.max_effector_displacement == 0.12


@pytest.mark.anyio
async def test_bake_effector_contact_camera_viewport() -> None:
    mock_response: dict[str, Any] = {
        "success": True,
        "clipPath": "Assets/Animations/Punch.anim",
        "effector": "right_hand",
        "backupId": "backup-punch-2",
        "keyframesModifiedCount": 16,
        "maxEffectorDisplacement": 0.08,
        "residualError": 0.003,
        "activeDuration": 0.35,
        "warnings": [],
    }

    with patch(
        "backend.bridge.client.UnityBridge.bake_effector_contact_native",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await bake_effector_contact(
            clip_path="Assets/Animations/Punch.anim",
            target_object_path="Characters/Fighter",
            effector="right_hand",
            target_type="camera_viewport",
            camera_name="Main Camera",
            viewport_coordinates=[0.5, 0.5],
            viewport_depth=0.25,
            time_range=[0.4, 0.6],
        )

    assert result.success is True
    assert result.effector == "right_hand"
    assert result.keyframes_modified_count == 16
