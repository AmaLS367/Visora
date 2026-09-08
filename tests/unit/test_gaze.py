from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas import CharacterGazeResult
from backend.tools.animation.gaze import solve_character_gaze


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeGazeBridge:
    def __init__(
        self,
        *,
        is_playing: bool = False,
        supported_features: set[str] | None = None,
        gaze_response: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._is_playing = is_playing
        self._supported_features = supported_features if supported_features is not None else {"character_gaze"}
        self.gaze_response = gaze_response or {
            "success": True,
            "targetObjectPath": "Characters/Hero",
            "targetLookAtPosition": [0.0, 1.7, 5.0],
            "totalTargetAngleDeg": 28.5,
            "isTargetBehindCharacter": False,
            "wasClamped": False,
            "residualGazeErrorDeg": 1.2,
            "solvedJoints": [
                {
                    "boneName": "Spine",
                    "localEuler": [1.5, 4.2, 0.0],
                    "localQuaternion": [0.013, 0.036, 0.0, 0.999],
                    "allocatedYawDeg": 4.2,
                    "allocatedPitchDeg": 1.5,
                    "wasClamped": False,
                },
                {
                    "boneName": "Neck",
                    "localEuler": [3.5, 10.0, 0.0],
                    "localQuaternion": [0.03, 0.087, 0.0, 0.996],
                    "allocatedYawDeg": 10.0,
                    "allocatedPitchDeg": 3.5,
                    "wasClamped": False,
                },
                {
                    "boneName": "Head",
                    "localEuler": [5.0, 14.3, 0.0],
                    "localQuaternion": [0.043, 0.124, 0.0, 0.991],
                    "allocatedYawDeg": 14.3,
                    "allocatedPitchDeg": 5.0,
                    "wasClamped": False,
                },
            ],
            "backupId": "backup-gaze-1",
            "warnings": [],
        }

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def solve_character_gaze_native(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("solve_character_gaze_native")
        return self.gaze_response


@pytest.mark.anyio
async def test_solve_character_gaze_validation_fails_on_missing_target() -> None:
    result = await solve_character_gaze(
        target_object_path="Hero",
    )
    assert not result.success
    assert "Either target_look_at_position or target_transform_path" in (result.error or "")


@pytest.mark.anyio
async def test_solve_character_gaze_rejects_play_mode_on_bake(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeGazeBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_character_gaze(
        target_object_path="Hero",
        target_look_at_position=[0.0, 1.7, 5.0],
        bake_to_clip="Assets/Look.anim",
        sample_time=1.0,
    )
    assert not result.success
    assert "Edit Mode" in (result.error or "")


@pytest.mark.anyio
async def test_solve_character_gaze_fails_when_capability_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeGazeBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_character_gaze(
        target_object_path="Hero",
        target_look_at_position=[0.0, 1.7, 5.0],
    )
    assert not result.success
    assert "character_gaze" in (result.error or "")


@pytest.mark.anyio
async def test_solve_character_gaze_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeGazeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_character_gaze(
        target_object_path="Characters/Hero",
        target_transform_path="camera:Main Camera",
        chest_weight=0.15,
        neck_weight=0.35,
        head_weight=0.50,
    )
    assert isinstance(result, CharacterGazeResult)
    assert result.success
    assert result.total_target_angle_deg == 28.5
    assert not result.is_target_behind_character
    assert not result.was_clamped
    assert len(result.solved_joints) == 3
    assert result.solved_joints[2].bone_name == "Head"
    assert result.solved_joints[2].allocated_yaw_deg == 14.3
    assert "solve_character_gaze_native" in bridge.calls
