from __future__ import annotations

from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas.contact_bake import BakeEffectorContactResult
from backend.tools.animation.contact_bake import bake_effector_contact


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeContactBakeBridge:
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
        self._supported_features = supported_features if supported_features is not None else {"effector_contact_baking"}
        self._raises = raises
        self.response = response or {
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

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def bake_effector_contact_native(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self.response


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


@pytest.mark.anyio
async def test_bake_effector_contact_world_point(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeContactBakeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await bake_effector_contact(
        clip_path="Assets/Animations/Kick.anim",
        target_object_path="Characters/Fighter",
        effector="right_foot",
        target_type="world_point",
        target_position=[0.0, 0.0, 1.2],
        time_range=[0.3, 0.6],
    )

    assert result.success is True
    assert result.effector == "right_foot"
    assert result.backup_id == "backup-kick-1"
    assert result.keyframes_modified_count == 24


@pytest.mark.anyio
async def test_bake_effector_contact_camera_viewport(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeContactBakeBridge(
        response={
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
    )
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

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


@pytest.mark.anyio
async def test_bake_effector_contact_omitted_time_range_not_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeContactBakeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    await bake_effector_contact(
        clip_path="Assets/Animations/Kick.anim",
        target_object_path="Characters/Fighter",
        effector="right_foot",
        target_position=[0.0, 0.0, 1.2],
    )
    assert bridge.calls[0]["time_range"] is None


@pytest.mark.anyio
async def test_bake_effector_contact_rejects_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeContactBakeBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await bake_effector_contact(
        clip_path="Assets/A.anim",
        target_object_path="Characters/Fighter",
        effector="right_foot",
        target_position=[0.0, 0.0, 1.0],
    )
    assert result.success is False
    assert "Edit Mode" in (result.error or "")
    assert bridge.calls == []


@pytest.mark.anyio
async def test_bake_effector_contact_fails_when_capability_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeContactBakeBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await bake_effector_contact(
        clip_path="Assets/A.anim",
        target_object_path="Characters/Fighter",
        effector="right_foot",
        target_position=[0.0, 0.0, 1.0],
    )
    assert result.success is False
    assert "effector_contact_baking" in (result.error or "")


@pytest.mark.anyio
async def test_bake_effector_contact_surfaces_bridge_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeContactBakeBridge(raises=RuntimeError("bridge unreachable"))
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await bake_effector_contact(
        clip_path="Assets/A.anim",
        target_object_path="Characters/Fighter",
        effector="right_foot",
        target_position=[0.0, 0.0, 1.0],
    )
    assert result.success is False
    assert "Bridge call failed" in (result.error or "")
