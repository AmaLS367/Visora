from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas import (
    AnimationComparisonResult,
    CurveDiscontinuityResult,
    JointMotionAnalysisResult,
)
from backend.tools.animation.qa import (
    analyze_joint_motion,
    compare_animation_previews,
    detect_curve_discontinuities,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeQABridge:
    def __init__(
        self,
        *,
        is_playing: bool = False,
        supported_features: set[str] | None = None,
        motion_response: dict[str, Any] | None = None,
        discontinuity_response: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._is_playing = is_playing
        self._supported_features = (
            supported_features
            if supported_features is not None
            else {"animation_motion_qa", "curve_discontinuity_detection"}
        )
        self.motion_response = motion_response or {
            "success": True,
            "clipPath": "Assets/Kick.anim",
            "targetObjectPath": "Characters/Hero",
            "clipDuration": 1.5,
            "sampleCount": 91,
            "sampleFps": 60.0,
            "overallSmoothnessScore": 0.88,
            "anomalies": [
                {
                    "timestamp": 0.45,
                    "boneName": "LeftLowerLeg",
                    "anomalyType": "jerk_spike",
                    "severity": "critical",
                    "metricValue": 250.0,
                    "threshold": 120.0,
                    "description": "Sudden jerk spike on knee",
                    "recommendation": "Smooth keyframe tangents",
                }
            ],
            "perBoneSummary": [
                {
                    "boneName": "LeftLowerLeg",
                    "peakVelocity": 4.5,
                    "peakAcceleration": 35.0,
                    "peakJerk": 250.0,
                    "averageJerk": 45.0,
                    "smoothnessScore": 0.75,
                }
            ],
            "recommendations": ["Smooth knee keyframes"],
            "warnings": [],
        }
        self.discontinuity_response = discontinuity_response or {
            "success": True,
            "clipPath": "Assets/Kick.anim",
            "discontinuitiesCount": 1,
            "items": [
                {
                    "curvePath": "Characters/Hero/LeftFoot",
                    "propertyName": "m_LocalRotation",
                    "timestamp": 0.5,
                    "issueType": "quaternion_flip",
                    "severity": "critical",
                    "currentValue": -0.85,
                    "description": "Antipodal flip detected",
                    "suggestedFix": "EnsureQuaternionContinuity",
                }
            ],
            "fixApplied": True,
            "backupId": "backup-flip-1",
            "warnings": [],
        }

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def analyze_joint_motion_native(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("analyze_joint_motion_native")
        return self.motion_response

    async def detect_curve_discontinuities_native(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("detect_curve_discontinuities_native")
        return self.discontinuity_response


@pytest.mark.anyio
async def test_analyze_joint_motion_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeQABridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_joint_motion(
        clip_path="Assets/Kick.anim",
        target_object_path="Characters/Hero",
    )
    assert not result.success
    assert "animation_motion_qa" in (result.error or "")


@pytest.mark.anyio
async def test_analyze_joint_motion_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeQABridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_joint_motion(
        clip_path="Assets/Kick.anim",
        target_object_path="Characters/Hero",
        sample_fps=60,
    )
    assert isinstance(result, JointMotionAnalysisResult)
    assert result.success
    assert result.overall_smoothness_score == 0.88
    assert len(result.anomalies) == 1
    assert result.anomalies[0].anomaly_type == "jerk_spike"
    assert result.anomalies[0].bone_name == "LeftLowerLeg"
    assert len(result.per_bone_summary) == 1
    assert "analyze_joint_motion_native" in bridge.calls


@pytest.mark.anyio
async def test_analyze_joint_motion_coerces_unknown_enum(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeQABridge(
        motion_response={
            "success": True,
            "clipPath": "Assets/Kick.anim",
            "targetObjectPath": "Characters/Hero",
            "overallSmoothnessScore": 0.9,
            "anomalies": [
                {
                    "timestamp": 0.2,
                    "boneName": "Hips",
                    "anomalyType": "velocity_reversal",
                    "severity": "info",
                    "metricValue": 1.0,
                    "threshold": 0.5,
                    "description": "x",
                    "recommendation": "y",
                }
            ],
            "perBoneSummary": [],
            "recommendations": [],
            "warnings": [],
        }
    )
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_joint_motion(clip_path="Assets/Kick.anim", target_object_path="Characters/Hero")
    assert result.success
    assert result.anomalies[0].anomaly_type == "unknown"
    assert result.anomalies[0].severity == "unknown"
    assert any("velocity_reversal" in w for w in result.warnings)


@pytest.mark.anyio
async def test_detect_curve_discontinuities_rejects_play_mode_on_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeQABridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await detect_curve_discontinuities(
        clip_path="Assets/Kick.anim",
        auto_fix=True,
    )
    assert not result.success
    assert "Edit Mode" in (result.error or "")


@pytest.mark.anyio
async def test_detect_curve_discontinuities_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeQABridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await detect_curve_discontinuities(
        clip_path="Assets/Kick.anim",
        auto_fix=True,
    )
    assert isinstance(result, CurveDiscontinuityResult)
    assert result.success
    assert result.discontinuities_count == 1
    assert result.fix_applied
    assert result.backup_id == "backup-flip-1"
    assert result.items[0].issue_type == "quaternion_flip"
    assert "detect_curve_discontinuities_native" in bridge.calls


@pytest.mark.anyio
async def test_compare_animation_previews_improvement() -> None:
    result = await compare_animation_previews(
        baseline_preview_id="prev-1",
        comparison_preview_id="prev-2",
        baseline_slide_distance=0.20,
        comparison_slide_distance=0.04,
        baseline_peak_jerk=200.0,
        comparison_peak_jerk=100.0,
    )
    assert isinstance(result, AnimationComparisonResult)
    assert result.success
    assert result.sliding_reduced_percent == 80.0
    assert result.jerk_reduced_percent == 50.0
    assert "Foot sliding reduced by 80.0%" in result.summary
    assert len(result.regression_warnings) == 0


@pytest.mark.anyio
async def test_compare_animation_previews_flags_regression() -> None:
    result = await compare_animation_previews(
        baseline_preview_id="prev-1",
        comparison_preview_id="prev-2",
        baseline_slide_distance=0.05,
        comparison_slide_distance=0.15,
        baseline_peak_jerk=100.0,
        comparison_peak_jerk=250.0,
    )
    assert isinstance(result, AnimationComparisonResult)
    assert result.success
    assert len(result.regression_warnings) >= 1
    assert "Regression" in result.regression_warnings[0]


@pytest.mark.anyio
async def test_compare_animation_previews_requires_baseline_metrics() -> None:
    result = await compare_animation_previews(
        baseline_preview_id="prev-1",
        comparison_preview_id="prev-2",
    )
    assert result.success is False
    assert "baseline" in (result.error or "").lower()
