from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas.transaction import (
    AnimationTransactionOperationModel,
    AnimationTransactionResult,
)
from backend.tools.animation.transaction import edit_animation_transaction


def test_transaction_schemas() -> None:
    op = AnimationTransactionOperationModel(
        operation_type="set_keyframe",
        clip_path="Assets/Animations/Walk.anim",
        target_path="Characters/Hero/Hips",
        time=0.5,
        values=[0.0, 1.0, 0.0],
    )
    assert op.operation_type == "set_keyframe"
    assert op.time == 0.5
    assert op.values == [0.0, 1.0, 0.0]

    res = AnimationTransactionResult(
        success=True,
        transaction_id="tx_test_123",
        applied_operations_count=3,
        keyframes_modified_count=12,
        backup_ids=["b1", "b2"],
        affected_clips=["Assets/Animations/Walk.anim"],
    )
    assert res.success is True
    assert res.applied_operations_count == 3
    assert res.rollback_performed is False


@pytest.mark.anyio
async def test_edit_animation_transaction_tool_success() -> None:
    mock_response: dict[str, Any] = {
        "success": True,
        "transactionId": "tx_test_999",
        "appliedOperationsCount": 2,
        "keyframesModifiedCount": 8,
        "rollbackPerformed": False,
        "backupIds": ["backup-1"],
        "affectedClips": ["Assets/Animations/Attack.anim"],
        "warnings": [],
    }

    with patch(
        "backend.bridge.client.UnityBridge.execute_animation_transaction_native",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await edit_animation_transaction(
            operations=[
                {
                    "operation_type": "set_keyframe",
                    "clip_path": "Assets/Animations/Attack.anim",
                    "time": 0.4,
                    "values": [1.0, 0.0, 0.0],
                },
                {
                    "operation_type": "create_event",
                    "clip_path": "Assets/Animations/Attack.anim",
                    "time": 0.4,
                    "function_name": "OnHit",
                },
            ],
            description="Test Transaction",
        )

    assert result.success is True
    assert result.transaction_id == "tx_test_999"
    assert result.applied_operations_count == 2
    assert result.keyframes_modified_count == 8
    assert result.rollback_performed is False
    assert result.backup_ids == ["backup-1"]


@pytest.mark.anyio
async def test_edit_animation_transaction_tool_rollback() -> None:
    mock_response: dict[str, Any] = {
        "success": False,
        "error": "Keyframe insertion failed at t=0.5s",
        "transactionId": "tx_fail_001",
        "appliedOperationsCount": 1,
        "keyframesModifiedCount": 0,
        "rollbackPerformed": True,
        "backupIds": ["backup-pre-tx"],
        "affectedClips": ["Assets/Animations/Run.anim"],
        "warnings": ["Rollback completed."],
    }

    with patch(
        "backend.bridge.client.UnityBridge.execute_animation_transaction_native",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await edit_animation_transaction(
            operations=[
                {
                    "operation_type": "set_keyframe",
                    "clip_path": "Assets/Animations/Run.anim",
                    "time": 0.5,
                }
            ]
        )

    assert result.success is False
    assert result.rollback_performed is True
    assert result.error is not None
    assert "Keyframe insertion failed" in result.error
