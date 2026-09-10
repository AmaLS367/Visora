from __future__ import annotations

from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas.transaction import (
    AnimationTransactionOperationModel,
    AnimationTransactionResult,
)
from backend.tools.animation.transaction import edit_animation_transaction


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeTransactionBridge:
    def __init__(
        self,
        *,
        is_playing: bool = False,
        supported_features: set[str] | None = None,
        response: dict[str, Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._is_playing = is_playing
        self._supported_features = supported_features if supported_features is not None else {"animation_transactions"}
        self._raises = raises
        self.response = response or {
            "success": True,
            "transactionId": "tx_test_999",
            "appliedOperationsCount": 1,
            "keyframesModifiedCount": 4,
            "rollbackPerformed": False,
            "backupIds": ["backup-1"],
            "affectedClips": ["Assets/Animations/Attack.anim"],
            "warnings": [],
        }

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def execute_animation_transaction_native(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self.response


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
async def test_edit_animation_transaction_tool_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge(
        response={
            "success": True,
            "transactionId": "tx_test_999",
            "appliedOperationsCount": 2,
            "keyframesModifiedCount": 8,
            "rollbackPerformed": False,
            "backupIds": ["backup-1"],
            "affectedClips": ["Assets/Animations/Attack.anim"],
            "warnings": [],
        }
    )
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

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
    assert result.backup_ids == ["backup-1"]


@pytest.mark.anyio
async def test_edit_animation_transaction_tool_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge(
        response={
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
    )
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

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


@pytest.mark.anyio
async def test_edit_animation_transaction_rejects_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await edit_animation_transaction(
        operations=[{"operation_type": "ensure_continuity", "clip_path": "Assets/A.anim"}]
    )
    assert result.success is False
    assert "Edit Mode" in (result.error or "")
    assert bridge.calls == []


@pytest.mark.anyio
async def test_edit_animation_transaction_fails_when_capability_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await edit_animation_transaction(
        operations=[{"operation_type": "ensure_continuity", "clip_path": "Assets/A.anim"}]
    )
    assert result.success is False
    assert "animation_transactions" in (result.error or "")


@pytest.mark.anyio
async def test_edit_animation_transaction_surfaces_bridge_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge(raises=RuntimeError("bridge unreachable"))
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await edit_animation_transaction(
        operations=[{"operation_type": "ensure_continuity", "clip_path": "Assets/A.anim"}]
    )
    assert result.success is False
    assert "Bridge call failed" in (result.error or "")


@pytest.mark.anyio
async def test_edit_animation_transaction_rejects_bad_tangent_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await edit_animation_transaction(
        operations=[
            {
                "operation_type": "set_keyframe",
                "clip_path": "Assets/A.anim",
                "property_name": "m_LocalPosition.x",
                "time": 1.0,
                "value": 0.0,
                "tangent_mode": "constant",
            }
        ]
    )
    assert result.success is False
    assert "tangent_mode" in (result.error or "")
    assert bridge.calls == []


@pytest.mark.anyio
async def test_edit_animation_transaction_hold_zero_value_sets_has_value(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    await edit_animation_transaction(
        operations=[
            {
                "operation_type": "set_keyframe_hold",
                "clip_path": "Assets/A.anim",
                "property_name": "m_LocalPosition.x",
                "start_time": 1.0,
                "duration": 0.5,
                "value": 0.0,
            }
        ]
    )
    sent_op = bridge.calls[0]["operations"][0]
    assert sent_op["hasValue"] is True
    assert sent_op["values"] == [0.0]


@pytest.mark.anyio
async def test_edit_animation_transaction_rejects_non_dict_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeTransactionBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await edit_animation_transaction(operations=["not-a-dict"])  # type: ignore[list-item]
    assert result.success is False
    assert "must be an object" in (result.error or "")
