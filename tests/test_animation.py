from typing import Any

import pytest

from backend.schemas import (
    AnimationBindingCurve,
    ClipInspectorResult,
    SampleAnimationResult,
    TransformPose,
)
from backend.tools import animation
from backend.tools.animation.analysis import (
    analyze_sampled_pose,
    detect_dangerous_curves,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeBridge:
    def __init__(self, execute_responses: list[dict[str, Any] | Exception] | None = None) -> None:
        self.execute_responses = list(execute_responses or [])
        self.executed_codes: list[str] = []

    async def execute_code(self, code: str) -> dict[str, Any]:
        self.executed_codes.append(code)
        if self.execute_responses:
            resp = self.execute_responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return {"success": True, "result": {"success": True}}


# ---------------------------------------------------------------------------
# Test Analysis Logic: Dangerous Curves & Pose Validation
# ---------------------------------------------------------------------------


def test_detect_dangerous_curves_clean() -> None:
    bindings = [
        AnimationBindingCurve(
            path="Root/Hips/Spine",
            property_name="m_LocalRotation.x",
            curve_type="rotation",
            keyframe_count=10,
            min_value=-0.5,
            max_value=0.5,
            start_value=0.0,
            end_value=0.0,
            is_constant=False,
        )
    ]
    warnings, metrics = detect_dangerous_curves(bindings, clip_length=1.0)
    assert len(warnings) == 0
    assert metrics["total_curves"] == 1
    assert metrics["rotation_curves_count"] == 1
    assert metrics["dangerous_curves_count"] == 0


def test_detect_dangerous_scale_curves() -> None:
    bindings = [
        # Negative scale curve
        AnimationBindingCurve(
            path="Root/Hips/LeftLeg",
            property_name="m_LocalScale.x",
            curve_type="scale",
            keyframe_count=5,
            min_value=-1.0,
            max_value=1.0,
            is_constant=False,
        ),
        # Dynamic positive scale on bone
        AnimationBindingCurve(
            path="Root/Hips/RightLeg",
            property_name="m_LocalScale.y",
            curve_type="scale",
            keyframe_count=5,
            min_value=0.8,
            max_value=1.5,
            is_constant=False,
        ),
    ]
    warnings, _metrics = detect_dangerous_curves(bindings, clip_length=1.0)
    assert len(warnings) == 2

    # Negative scale should be critical
    crit = [w for w in warnings if w.risk_level == "critical"]
    assert len(crit) == 1
    assert "Negative scale" in crit[0].reason

    # Dynamic scale should be warning
    warn = [w for w in warnings if w.risk_level == "warning"]
    assert len(warn) == 1
    assert "Animated bone scale" in warn[0].reason


def test_detect_dangerous_position_curves() -> None:
    bindings = [
        # Child bone with local position animation
        AnimationBindingCurve(
            path="Root/Hips/LeftArm/LeftHand",
            property_name="m_LocalPosition.x",
            curve_type="position",
            keyframe_count=8,
            min_value=0.1,
            max_value=0.9,
            is_constant=False,
        ),
        # Root bone with extreme displacement
        AnimationBindingCurve(
            path="Root",
            property_name="m_LocalPosition.z",
            curve_type="position",
            keyframe_count=12,
            min_value=0.0,
            max_value=120.0,
            is_constant=False,
        ),
    ]
    warnings, _metrics = detect_dangerous_curves(bindings, clip_length=2.0)
    assert len(warnings) == 2
    reasons = [w.reason for w in warnings]
    assert "Local position animation on non-root bone" in reasons
    assert "Large root displacement" in reasons


def test_detect_static_flat_curves() -> None:
    bindings = [
        AnimationBindingCurve(
            path="Root/Hips",
            property_name="m_LocalPosition.y",
            curve_type="position",
            keyframe_count=10,
            min_value=1.0,
            max_value=1.0,
            start_value=1.0,
            end_value=1.0,
            is_constant=True,
        )
    ]
    warnings, metrics = detect_dangerous_curves(bindings, clip_length=1.0)
    assert len(warnings) == 1
    assert warnings[0].risk_level == "info"
    assert "Static flat curve" in warnings[0].reason
    assert metrics["constant_curves_count"] == 1


def test_detect_nan_and_extreme_values() -> None:
    bindings = [
        AnimationBindingCurve(
            path="Root",
            property_name="m_LocalPosition.x",
            curve_type="position",
            keyframe_count=3,
            min_value=float("nan"),
            max_value=1.0,
            is_constant=False,
        ),
        AnimationBindingCurve(
            path="Root",
            property_name="m_LocalPosition.y",
            curve_type="position",
            keyframe_count=3,
            min_value=0.0,
            max_value=5000.0,
            is_constant=False,
        ),
    ]
    warnings, _metrics = detect_dangerous_curves(bindings, clip_length=1.0)
    crit = [w for w in warnings if w.risk_level == "critical"]
    assert len(crit) == 2
    assert any("NaN" in w.reason for w in crit)
    assert any("Extreme keyframe value" in w.reason for w in crit)


def test_analyze_sampled_pose_anomalies() -> None:
    poses = {
        "Root": TransformPose(
            path="Root",
            name="Root",
            local_position=[0.0, 0.0, 0.0],
            local_scale=[-1.0, 1.0, 1.0],  # Negative scale anomaly
            world_position=[0.0, -60.0, 0.0],  # Sub-ground warning
        ),
        "Root/Bone": TransformPose(
            path="Root/Bone",
            name="Bone",
            local_scale=[25.0, 25.0, 25.0],  # Extreme scale warning
        ),
    }
    anomalies, warnings = analyze_sampled_pose(poses)
    assert any("Negative local scale" in a for a in anomalies)
    assert any("below ground" in w for w in warnings)
    assert any("Abnormal local scale" in w for w in warnings)


def test_analyze_sampled_pose_nan() -> None:
    poses = {
        "Root": TransformPose(
            path="Root",
            name="Root",
            local_position=[float("nan"), 0.0, 0.0],
        )
    }
    anomalies, _warnings = analyze_sampled_pose(poses)
    assert any("NaN or Infinite" in a for a in anomalies)


# ---------------------------------------------------------------------------
# Test MCP Tools: inspect_animation_clip & clip_inspector
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_inspect_animation_clip_success(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "RoverRun",
            "clipPath": "Assets/Animations/RoverRun.anim",
            "length": 1.5,
            "fps": 60.0,
            "loopTime": True,
            "wrapMode": "Loop",
            "isLegacy": False,
            "hasRootMotion": True,
            "bindings": [
                {
                    "path": "Hips",
                    "propertyName": "m_LocalPosition.x",
                    "typeName": "UnityEngine.Transform",
                    "curveType": "position",
                    "keyframeCount": 10,
                    "minValue": -0.2,
                    "maxValue": 0.2,
                    "startValue": 0.0,
                    "endValue": 0.0,
                    "isConstant": False,
                },
                {
                    "path": "Hips/LeftUpLeg",
                    "propertyName": "m_LocalScale.x",
                    "typeName": "UnityEngine.Transform",
                    "curveType": "scale",
                    "keyframeCount": 5,
                    "minValue": 0.9,
                    "maxValue": 1.1,
                    "startValue": 1.0,
                    "endValue": 1.0,
                    "isConstant": False,
                },
            ],
            "events": [
                {
                    "time": 0.75,
                    "functionName": "OnFootstep",
                    "stringParam": "left",
                    "floatParam": 1.0,
                    "intParam": 0,
                }
            ],
        },
    }

    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.inspect_animation_clip("Assets/Animations/RoverRun.anim")

    assert isinstance(result, ClipInspectorResult)
    assert result.success is True
    assert result.clip_name == "RoverRun"
    assert result.length == 1.5
    assert result.fps == 60.0
    assert result.loop_time is True
    assert result.has_root_motion is True
    assert result.curves_count == 2
    assert result.events_count == 1
    assert len(result.bindings) == 2
    assert len(result.events) == 1
    assert result.events[0].function_name == "OnFootstep"

    # Scale curve should trigger a warning
    assert len(result.dangerous_curves) >= 1
    assert any("Animated bone scale" in w.reason for w in result.dangerous_curves)


@pytest.mark.anyio
async def test_inspect_animation_clip_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": False,
            "error": "AnimationClip not found at path: Assets/NonExistent.anim",
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.inspect_animation_clip("Assets/NonExistent.anim")

    assert result.success is False
    assert "not found" in (result.error or "")


@pytest.mark.anyio
async def test_inspect_animation_clip_bridge_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(execute_responses=[ConnectionError("Bridge disconnected")])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.inspect_animation_clip("Assets/Test.anim")

    assert result.success is False
    assert "Bridge disconnected" in (result.error or "")


@pytest.mark.anyio
async def test_clip_inspector_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "AliasClip",
            "length": 2.0,
            "fps": 30.0,
            "loopTime": False,
            "bindings": [],
            "events": [],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.clip_inspector("Assets/AliasClip.anim")
    assert result.success is True
    assert result.clip_name == "AliasClip"
    assert result.length == 2.0


# ---------------------------------------------------------------------------
# Test MCP Tools: sample_animation_clip
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sample_animation_clip_by_time(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "Walk",
            "clipPath": "Assets/Walk.anim",
            "targetPath": "Player/Armature",
            "sampleTime": 0.5,
            "poseRestored": True,
            "sampledTransforms": {
                "": {
                    "path": "",
                    "name": "Armature",
                    "localPosition": [0.0, 0.0, 0.5],
                    "localRotationEuler": [0.0, 0.0, 0.0],
                    "localScale": [1.0, 1.0, 1.0],
                    "worldPosition": [0.0, 0.0, 0.5],
                },
                "Hips": {
                    "path": "Hips",
                    "name": "Hips",
                    "localPosition": [0.0, 1.0, 0.0],
                    "localRotationEuler": [5.0, 0.0, 0.0],
                    "localScale": [1.0, 1.0, 1.0],
                },
            },
            "rootMotionDelta": [0.0, 0.0, 0.5],
        },
    }

    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.sample_animation_clip(
        target_game_object_path="Player/Armature",
        clip_path="Assets/Walk.anim",
        time=0.5,
        restore_pose_after=True,
    )

    assert isinstance(result, SampleAnimationResult)
    assert result.success is True
    assert result.clip_name == "Walk"
    assert result.sample_time == 0.5
    assert result.pose_restored is True
    assert len(result.sampled_transforms) == 2
    assert "Hips" in result.sampled_transforms
    assert result.sampled_transforms["Hips"].local_rotation_euler == [5.0, 0.0, 0.0]
    assert result.root_motion_delta == [0.0, 0.0, 0.5]
    assert len(result.anomalies_detected) == 0


@pytest.mark.anyio
async def test_sample_animation_clip_by_normalized_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # First call is inspect_animation_clip to get duration
    inspect_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "Walk",
            "length": 2.0,
            "fps": 30.0,
            "bindings": [],
            "events": [],
        },
    }
    sample_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "Walk",
            "sampleTime": 1.0,  # 0.5 * 2.0s
            "poseRestored": True,
            "sampledTransforms": {
                "": {
                    "path": "",
                    "name": "Root",
                    "localPosition": [0.0, 0.0, 1.0],
                    "localRotationEuler": [0.0, 0.0, 0.0],
                    "localScale": [1.0, 1.0, 1.0],
                }
            },
            "rootMotionDelta": [0.0, 0.0, 1.0],
        },
    }

    fake_bridge = FakeBridge(execute_responses=[inspect_response, sample_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.sample_animation_clip(
        target_game_object_path="Character",
        clip_path="Assets/Walk.anim",
        normalized_time=0.5,
    )

    assert result.success is True
    assert result.sample_time == 1.0
    assert result.normalized_time == 0.5


@pytest.mark.anyio
async def test_sample_animation_clip_target_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": False,
            "error": "Target GameObject not found at hierarchy path: MissingPlayer",
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.sample_animation_clip(
        target_game_object_path="MissingPlayer",
        clip_path="Assets/Walk.anim",
        time=0.0,
    )

    assert result.success is False
    assert "Target GameObject not found" in (result.error or "")


@pytest.mark.anyio
async def test_sample_animation_clip_with_anomalies(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "BrokenClip",
            "sampledTransforms": {
                "Hips": {
                    "path": "Hips",
                    "name": "Hips",
                    "localPosition": [0.0, 0.0, 0.0],
                    "localRotationEuler": [0.0, 0.0, 0.0],
                    "localScale": [-1.0, 1.0, 1.0],  # Negative scale anomaly
                }
            },
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.sample_animation_clip(
        target_game_object_path="Character",
        clip_path="Assets/Broken.anim",
        time=0.1,
    )

    assert result.success is True
    assert len(result.anomalies_detected) >= 1
    assert any("Negative local scale" in a for a in result.anomalies_detected)


@pytest.mark.anyio
async def test_analyze_animation_curves_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "Jump",
            "length": 1.0,
            "fps": 30.0,
            "bindings": [
                {
                    "path": "Root",
                    "propertyName": "m_LocalPosition.y",
                    "curveType": "position",
                    "keyframeCount": 5,
                    "minValue": 0.0,
                    "maxValue": 2.0,
                    "isConstant": False,
                }
            ],
            "events": [],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.analyze_animation_curves("Assets/Jump.anim")
    assert result.success is True
    assert result.clip_name == "Jump"
    assert result.curves_count == 1
