from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas import (
    BakeContactConstraintsResult,
    ContactAnalysisResult,
)
from backend.tools.animation.contact import (
    analyze_contact_constraints,
    bake_contact_constraints,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeContactBridge:
    def __init__(
        self,
        *,
        is_playing: bool = False,
        supported_features: set[str] | None = None,
        analyze_response: dict[str, Any] | None = None,
        bake_response: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._is_playing = is_playing
        self._supported_features = (
            supported_features if supported_features is not None else {"humanoid_contact_constraints"}
        )
        self.analyze_response = analyze_response or {
            "success": True,
            "clipPath": "Assets/Animations/Run.anim",
            "targetObjectPath": "Runner",
            "supportedEffectors": [
                {
                    "effector": "left_foot",
                    "isSupported": True,
                    "rootBone": "LeftUpperLeg",
                    "midBone": "LeftLowerLeg",
                    "endBone": "LeftFoot",
                    "limbLength": 0.85,
                },
                {
                    "effector": "right_foot",
                    "isSupported": True,
                    "rootBone": "RightUpperLeg",
                    "midBone": "RightLowerLeg",
                    "endBone": "RightFoot",
                    "limbLength": 0.85,
                },
            ],
            "unsupportedEffectors": [],
            "contactPhases": [
                {
                    "effector": "left_foot",
                    "startTime": 0.2,
                    "endTime": 0.6,
                    "duration": 0.4,
                    "averagePosition": [0.2, 0.0, 0.5],
                    "isSliding": True,
                    "slideDistance": 0.06,
                }
            ],
            "anomalies": [
                {
                    "effector": "left_foot",
                    "anomalyType": "foot_sliding",
                    "startTime": 0.2,
                    "endTime": 0.6,
                    "severity": "warning",
                    "value": 0.06,
                    "description": "Foot sliding detected on 'left_foot' (6.0cm).",
                },
                {
                    "effector": "right_foot",
                    "anomalyType": "ground_penetration",
                    "startTime": 0.8,
                    "endTime": 0.9,
                    "severity": "critical",
                    "value": 0.03,
                    "description": "Foot penetrates ground by 3.0cm.",
                },
            ],
            "totalSlideDistance": 0.06,
            "maxGroundPenetration": 0.03,
            "warnings": [],
        }
        self.bake_response = bake_response or {
            "success": True,
            "sourceClipPath": "Assets/Animations/Run.anim",
            "outputClipPath": "Assets/Animations/Run.anim",
            "backupId": "Run_backup_123.anim",
            "effectorsBaked": ["left_foot", "right_foot"],
            "keyframesModifiedCount": 64,
            "slideReductionPercent": 85.0,
            "warnings": [],
        }

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def analyze_contact_constraints(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("analyze")
        return self.analyze_response

    async def bake_contact_constraints(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("bake")
        return self.bake_response


# Contact analysis tests


@pytest.mark.anyio
async def test_analyze_contact_constraints_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeContactBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await analyze_contact_constraints(
        target_object_path="Runner",
        clip_path="Assets/Animations/Run.anim",
        effectors=["left_foot", "right_foot"],
    )

    assert isinstance(result, ContactAnalysisResult)
    assert result.success is True
    assert len(result.supported_effectors) == 2
    assert result.supported_effectors[0].effector == "left_foot"
    assert result.supported_effectors[0].is_supported is True
    assert len(result.contact_phases) == 1
    assert result.contact_phases[0].is_sliding is True
    assert result.contact_phases[0].slide_distance == 0.06
    assert len(result.anomalies) == 2
    assert result.total_slide_distance == 0.06
    assert result.max_ground_penetration == 0.03
    assert "analyze" in fake.calls


@pytest.mark.anyio
async def test_analyze_contact_constraints_unsupported_limbs(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeContactBridge(
        analyze_response={
            "success": True,
            "clipPath": "Assets/Clips/Jump.anim",
            "targetObjectPath": "Creature",
            "supportedEffectors": [],
            "unsupportedEffectors": [
                {
                    "effector": "left_foot",
                    "isSupported": False,
                    "blockerReason": "Missing Two-Bone chain joints for 'left_foot': lower bone.",
                }
            ],
            "contactPhases": [],
            "anomalies": [],
            "totalSlideDistance": 0.0,
            "maxGroundPenetration": 0.0,
            "warnings": ["No supported limb effectors found to analyze."],
        }
    )
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await analyze_contact_constraints(
        target_object_path="Creature",
        clip_path="Assets/Clips/Jump.anim",
    )

    assert result.success is True
    assert len(result.supported_effectors) == 0
    assert len(result.unsupported_effectors) == 1
    assert result.unsupported_effectors[0].is_supported is False
    assert "Missing Two-Bone chain joints" in (result.unsupported_effectors[0].blocker_reason or "")


@pytest.mark.anyio
async def test_analyze_contact_constraints_unsupported_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeContactBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await analyze_contact_constraints(
        target_object_path="Character",
        clip_path="Assets/Clip.anim",
    )

    assert result.success is False
    assert "does not support capability" in (result.error or "")


# Contact baking tests


@pytest.mark.anyio
async def test_bake_contact_constraints_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeContactBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await bake_contact_constraints(
        clip_path="Assets/Animations/Run.anim",
        target_object_path="Runner",
        effectors=["left_foot", "right_foot"],
        fix_foot_sliding=True,
        fix_penetration=True,
    )

    assert isinstance(result, BakeContactConstraintsResult)
    assert result.success is True
    assert result.output_clip_path == "Assets/Animations/Run.anim"
    assert result.backup_id == "Run_backup_123.anim"
    assert result.keyframes_modified_count == 64
    assert result.slide_reduction_percent == 85.0
    assert "left_foot" in result.effectors_baked
    assert "bake" in fake.calls


@pytest.mark.anyio
async def test_bake_contact_constraints_clones_embedded_clip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeContactBridge(
        bake_response={
            "success": True,
            "sourceClipPath": "Assets/Characters/Model.fbx",
            "outputClipPath": "Assets/Animations/Walk_ContactBaked.anim",
            "backupId": None,
            "effectorsBaked": ["left_foot"],
            "keyframesModifiedCount": 32,
            "slideReductionPercent": 85.0,
            "warnings": [
                "Source clip was embedded/read-only. Cloned to standalone writable asset: 'Assets/Animations/Walk_ContactBaked.anim'."
            ],
        }
    )
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await bake_contact_constraints(
        clip_path="Assets/Characters/Model.fbx",
        target_object_path="Runner",
    )

    assert result.success is True
    assert result.output_clip_path == "Assets/Animations/Walk_ContactBaked.anim"
    assert any("embedded/read-only" in w for w in result.warnings)


@pytest.mark.anyio
async def test_bake_contact_constraints_play_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeContactBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await bake_contact_constraints(
        clip_path="Assets/Animations/Run.anim",
        target_object_path="Runner",
    )

    assert result.success is False
    assert "Edit Mode" in (result.error or "")
    assert fake.calls == []


@pytest.mark.anyio
async def test_bake_contact_constraints_unsupported_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeContactBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await bake_contact_constraints(
        clip_path="Assets/Clip.anim",
        target_object_path="Runner",
    )

    assert result.success is False
    assert "does not support capability" in (result.error or "")
