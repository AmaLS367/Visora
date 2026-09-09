from __future__ import annotations

from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas.camera_action import CameraSubjectContactResult
from backend.tools.animation.camera_action import solve_camera_subject_contact


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeCameraActionBridge:
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
        self._supported_features = supported_features if supported_features is not None else {"camera_subject_action"}
        self._raises = raises
        self.response = response or {
            "success": True,
            "characterBackupId": "char-backup-dropkick",
            "cameraBackupId": "cam-backup-recoil",
            "impactWorldPosition": [0.1, 1.3, -0.4],
            "impactScreenResidualPixels": [2.1, 1.5],
            "maxLimbReachRatio": 0.91,
            "keyframesModifiedCount": 24,
            "warnings": [],
        }

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def solve_camera_subject_contact_native(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self.response


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
async def test_solve_camera_subject_contact_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeCameraActionBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_camera_subject_contact(
        character_path="Characters/Hero",
        character_clip_path="Assets/Animations/Hero_Dropkick.anim",
        camera_name="Main Camera",
        camera_clip_path="Assets/Animations/Camera_Action.anim",
        effector="right_foot",
        impact_time=0.6,
        lens_viewport=[0.5, 0.5],
        camera_recoil_impulse=[0.0, -0.2, -0.5],
    )

    assert result.success is True
    assert result.character_backup_id == "char-backup-dropkick"
    assert result.camera_backup_id == "cam-backup-recoil"
    assert result.max_limb_reach_ratio == 0.91


@pytest.mark.anyio
async def test_solve_camera_subject_contact_rejects_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeCameraActionBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_camera_subject_contact(
        character_path="Characters/Hero",
        character_clip_path="Assets/A.anim",
        camera_name="Main Camera",
    )
    assert result.success is False
    assert "Edit Mode" in (result.error or "")
    assert bridge.calls == []


@pytest.mark.anyio
async def test_solve_camera_subject_contact_fails_when_capability_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeCameraActionBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_camera_subject_contact(
        character_path="Characters/Hero",
        character_clip_path="Assets/A.anim",
        camera_name="Main Camera",
    )
    assert result.success is False
    assert "camera_subject_action" in (result.error or "")


@pytest.mark.anyio
async def test_solve_camera_subject_contact_surfaces_bridge_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeCameraActionBridge(raises=RuntimeError("bridge unreachable"))
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_camera_subject_contact(
        character_path="Characters/Hero",
        character_clip_path="Assets/A.anim",
        camera_name="Main Camera",
    )
    assert result.success is False
    assert "Bridge call failed" in (result.error or "")


@pytest.mark.anyio
async def test_solve_camera_subject_contact_validates_lens_viewport(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeCameraActionBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_camera_subject_contact(
        character_path="Characters/Hero",
        character_clip_path="Assets/A.anim",
        camera_name="Main Camera",
        lens_viewport=[0.5],
    )
    assert result.success is False
    assert "lens_viewport" in (result.error or "")
    assert bridge.calls == []
