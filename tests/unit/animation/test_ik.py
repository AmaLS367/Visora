from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas import (
    TwoBoneIKSolveResult,
    ViewportEffectorPlacementResult,
)
from backend.tools.animation.ik import (
    place_effector_in_viewport,
    solve_two_bone_ik,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeIKBridge:
    def __init__(
        self,
        *,
        is_playing: bool = False,
        supported_features: set[str] | None = None,
        ik_response: dict[str, Any] | None = None,
        viewport_response: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._is_playing = is_playing
        self._supported_features = (
            supported_features if supported_features is not None else {"inverse_kinematics", "viewport_placement"}
        )
        self.ik_response = ik_response or {
            "success": True,
            "targetObjectPath": "Characters/Hero",
            "effector": "left_foot",
            "rootBone": "LeftUpperLeg",
            "midBone": "LeftLowerLeg",
            "endBone": "LeftFoot",
            "rootRotationEuler": [25.0, 0.0, 0.0],
            "rootRotationQuaternion": [0.216, 0.0, 0.0, 0.976],
            "midRotationEuler": [45.0, 0.0, 0.0],
            "midRotationQuaternion": [0.383, 0.0, 0.0, 0.924],
            "endRotationEuler": [-15.0, 0.0, 0.0],
            "endRotationQuaternion": [-0.131, 0.0, 0.0, 0.991],
            "targetClamped": False,
            "reachDistance": 0.92,
            "actualDistance": 0.75,
            "positionResidual": 0.002,
            "rotationResidualDeg": 0.5,
            "backupId": "backup-123",
            "warnings": [],
        }
        self.viewport_response = viewport_response or {
            "success": True,
            "cameraName": "Main Camera",
            "targetObjectPath": "Characters/Hero",
            "effector": "left_foot",
            "targetWorldPosition": [0.0, 1.2, 0.25],
            "solvedWorldPosition": [0.001, 1.201, 0.251],
            "actualViewport": [0.501, 0.501, 0.251],
            "screenResidualPixels": [1.92, 1.08],
            "depthResidualMeters": 0.001,
            "isInFrustum": True,
            "isClippedByNearPlane": False,
            "reachDistance": 0.92,
            "actualDistance": 0.75,
            "targetClamped": False,
            "ikResult": self.ik_response,
            "warnings": [],
        }

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def solve_two_bone_ik_native(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("solve_two_bone_ik_native")
        return self.ik_response

    async def place_effector_in_viewport_native(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("place_effector_in_viewport_native")
        return self.viewport_response


@pytest.mark.anyio
async def test_solve_two_bone_ik_validation_fails_on_short_position() -> None:
    result = await solve_two_bone_ik(
        target_object_path="Hero",
        target_position=[1.0, 2.0],  # only 2 elements
    )
    assert not result.success
    assert "at least 3 coordinates" in (result.error or "")


@pytest.mark.anyio
async def test_solve_two_bone_ik_rejects_play_mode_on_bake(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIKBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_two_bone_ik(
        target_object_path="Hero",
        target_position=[0.0, 0.0, 0.5],
        bake_to_clip="Assets/Kick.anim",
        sample_time=0.5,
    )
    assert not result.success
    assert "Edit Mode" in (result.error or "")


@pytest.mark.anyio
async def test_solve_two_bone_ik_fails_when_capability_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIKBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_two_bone_ik(
        target_object_path="Hero",
        target_position=[0.0, 0.0, 0.5],
    )
    assert not result.success
    assert "inverse_kinematics" in (result.error or "")


@pytest.mark.anyio
async def test_solve_two_bone_ik_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIKBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await solve_two_bone_ik(
        target_object_path="Characters/Hero",
        target_position=[0.2, 0.0, 0.5],
        effector="left_foot",
        pole_vector=[0.2, 0.5, 1.0],
        weight=1.0,
    )
    assert isinstance(result, TwoBoneIKSolveResult)
    assert result.success
    assert result.effector == "left_foot"
    assert result.root_bone == "LeftUpperLeg"
    assert result.reach_distance == 0.92
    assert result.position_residual == 0.002
    assert "solve_two_bone_ik_native" in bridge.calls


@pytest.mark.anyio
async def test_solve_two_bone_ik_requires_sample_time_for_bake() -> None:
    result = await solve_two_bone_ik(
        target_object_path="Hero",
        target_position=[0.0, 0.0, 0.5],
        bake_to_clip="Assets/Run.anim",
    )
    assert not result.success
    assert "sample_time is required" in (result.error or "")


@pytest.mark.anyio
async def test_place_effector_in_viewport_validation_fails_on_zero_depth() -> None:
    result = await place_effector_in_viewport(
        target_object_path="Hero",
        camera_depth=0.0,
    )
    assert not result.success
    assert "camera_depth must be greater than 0.001" in (result.error or "")


@pytest.mark.anyio
async def test_place_effector_in_viewport_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIKBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await place_effector_in_viewport(
        target_object_path="Characters/Hero",
        effector="left_foot",
        camera_name="Main Camera",
        viewport_x=0.5,
        viewport_y=0.5,
        camera_depth=0.25,
        align_mode="face_camera",
    )
    assert isinstance(result, ViewportEffectorPlacementResult)
    assert result.success
    assert result.camera_name == "Main Camera"
    assert result.is_in_frustum
    assert not result.is_clipped_by_near_plane
    assert result.depth_residual_meters == 0.001
    assert result.ik_result is not None
    assert result.ik_result.success
    assert "place_effector_in_viewport_native" in bridge.calls
