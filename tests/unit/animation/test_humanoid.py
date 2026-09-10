from typing import Any

import pytest

import backend.tools.animation as animation_pkg
from backend.schemas import (
    AnimationBindingCurve,
    AnimationPreviewMotionSummary,
    AnimationPreviewResult,
    AvatarBlocker,
    ClipInspectorResult,
    HumanoidConfigurationResult,
    HumanoidRetargetPreviewResult,
    HumanoidValidationResult,
    TPoseAssessment,
)
from backend.tools.animation.humanoid import (
    configure_humanoid_avatar,
    preview_humanoid_retarget,
    validate_humanoid_avatar,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeHumanoidBridge:
    def __init__(
        self,
        *,
        is_playing: bool = False,
        supported_features: set[str] | None = None,
        validate_response: dict[str, Any] | None = None,
        configure_response: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._is_playing = is_playing
        self._supported_features = (
            supported_features
            if supported_features is not None
            else {
                "humanoid_avatar_diagnostics",
                "humanoid_avatar_configuration",
            }
        )
        self.validate_response = validate_response or {
            "success": True,
            "targetPath": "Character",
            "isValidHumanoid": True,
            "avatarStatus": "valid_humanoid",
            "blockers": [],
            "missingRequiredBones": [],
            "missingOptionalBones": [],
            "boneMappings": {"Hips": "Hips", "Spine": "Spine"},
            "posture": {
                "armsHorizontalAngle": 88.5,
                "legsVerticalAngle": 2.0,
                "isTpose": True,
                "isApose": False,
                "symmetryScore": 0.98,
                "warnings": [],
            },
            "warnings": [],
        }
        self.configure_response = configure_response or {
            "success": True,
            "assetPath": "Assets/Model.fbx",
            "animationType": "Human",
            "avatarCreated": True,
            "avatarValid": True,
            "configuredBonesCount": 15,
            "blockers": [],
            "warnings": [],
        }

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self._is_playing}

    async def validate_humanoid_avatar(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("validate")
        return self.validate_response

    async def configure_humanoid_avatar(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("configure")
        return self.configure_response


# Validation tests


@pytest.mark.anyio
async def test_validate_humanoid_avatar_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await validate_humanoid_avatar(target_path="Character")

    assert isinstance(result, HumanoidValidationResult)
    assert result.success is True
    assert result.is_valid_humanoid is True
    assert result.avatar_status == "valid_humanoid"
    assert result.posture is not None
    assert result.posture.is_tpose is True
    assert result.blockers == []
    assert "validate" in fake.calls


@pytest.mark.anyio
async def test_validate_humanoid_avatar_blockers_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge(
        validate_response={
            "success": True,
            "targetPath": "BrokenCharacter",
            "isValidHumanoid": False,
            "avatarStatus": "invalid_avatar",
            "blockers": [
                {
                    "boneName": "LeftUpperArm",
                    "category": "missing_bone",
                    "severity": "blocker",
                    "message": "Required bone 'LeftUpperArm' is missing.",
                    "suggestedFix": "Map bone to LeftUpperArm.",
                },
                {
                    "boneName": "Arms",
                    "category": "posture",
                    "severity": "warning",
                    "message": "Arms are in A-pose.",
                    "suggestedFix": "Adjust to T-pose.",
                },
            ],
            "missingRequiredBones": ["LeftUpperArm"],
            "missingOptionalBones": ["Chest"],
            "boneMappings": {},
            "posture": {
                "armsHorizontalAngle": 48.0,
                "legsVerticalAngle": 5.0,
                "isTpose": False,
                "isApose": True,
                "symmetryScore": 0.9,
                "warnings": [],
            },
            "warnings": ["Inspection found blockers."],
        }
    )
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await validate_humanoid_avatar(target_path="BrokenCharacter")

    assert result.success is True
    assert result.is_valid_humanoid is False
    assert len(result.blockers) == 2
    assert result.blockers[0].severity == "blocker"
    assert result.blockers[0].category == "missing_bone"
    assert result.blockers[1].severity == "warning"
    assert result.missing_required_bones == ["LeftUpperArm"]
    assert result.posture is not None
    assert result.posture.is_apose is True


@pytest.mark.anyio
async def test_validate_humanoid_avatar_no_arguments() -> None:
    result = await validate_humanoid_avatar()
    assert result.success is False
    assert "Either target_path or asset_path must be provided" in (result.error or "")


@pytest.mark.anyio
async def test_validate_humanoid_avatar_unsupported_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await validate_humanoid_avatar(asset_path="Assets/Model.fbx")
    assert result.success is False
    assert "does not support capability" in (result.error or "")


# Configuration tests


@pytest.mark.anyio
async def test_configure_humanoid_avatar_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await configure_humanoid_avatar(
        asset_path="Assets/Model.fbx",
        bone_mapping_overrides={"Hips": "pelvis", "Spine": "spine_01"},
    )

    assert isinstance(result, HumanoidConfigurationResult)
    assert result.success is True
    assert result.avatar_created is True
    assert result.avatar_valid is True
    assert result.configured_bones_count == 15
    assert "configure" in fake.calls


@pytest.mark.anyio
async def test_configure_humanoid_avatar_play_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await configure_humanoid_avatar(asset_path="Assets/Model.fbx")

    assert result.success is False
    assert "Edit Mode" in (result.error or "")
    assert fake.calls == []


@pytest.mark.anyio
async def test_configure_humanoid_avatar_unsupported_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await configure_humanoid_avatar(asset_path="Assets/Model.fbx")

    assert result.success is False
    assert "does not support capability" in (result.error or "")


# Retarget preview tests


@pytest.mark.anyio
async def test_preview_humanoid_retarget_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    async def mock_inspect(_clip_path: str) -> ClipInspectorResult:
        return ClipInspectorResult(
            success=True,
            clip_name="Walk",
            bindings=[
                AnimationBindingCurve(
                    path="",
                    property_name="RootT.x",
                    type_name="UnityEngine.Animator",
                    curve_type="float_property",
                    keyframe_count=10,
                )
            ],
        )

    async def mock_preview(**kwargs: Any) -> AnimationPreviewResult:
        return AnimationPreviewResult(
            success=True,
            clip_path=kwargs["clip_path"],
            target_object_path=kwargs["target_object_path"],
            camera_name=kwargs["camera_name"],
            rendered_camera_name=kwargs["camera_name"],
            fps=kwargs["fps"],
            width=kwargs["width"],
            height=kwargs["height"],
            motion_summary=AnimationPreviewMotionSummary(
                peak_motion_timestamp=0.5,
                peak_changed_pixel_ratio=0.2,
                mean_changed_pixel_ratio=0.1,
                is_static=False,
            ),
            recommended_interpretation="Ready for review.",
        )

    monkeypatch.setattr("backend.tools.animation.inspector.inspect_animation_clip", mock_inspect)
    monkeypatch.setattr("backend.tools.animation.humanoid.preview_animation", mock_preview)

    result = await preview_humanoid_retarget(
        target_object_path="Character",
        clip_path="Assets/Mocap/Walk.anim",
    )

    assert isinstance(result, HumanoidRetargetPreviewResult)
    assert result.success is True
    assert result.is_compatible is True
    assert result.source_avatar_type == "humanoid"
    assert result.target_avatar_type == "humanoid"
    assert result.preview is not None
    assert result.detected_retarget_issues == []


@pytest.mark.anyio
async def test_preview_humanoid_retarget_incompatible_target(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeHumanoidBridge(
        validate_response={
            "success": True,
            "targetPath": "GenericCharacter",
            "isValidHumanoid": False,
            "avatarStatus": "generic_avatar",
            "blockers": [],
            "missingRequiredBones": ["Head"],
            "missingOptionalBones": [],
            "boneMappings": {},
            "warnings": [],
        }
    )
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    async def mock_inspect(_clip_path: str) -> ClipInspectorResult:
        return ClipInspectorResult(success=True, clip_name="Walk", bindings=[])

    async def mock_preview(**kwargs: Any) -> AnimationPreviewResult:
        return AnimationPreviewResult(
            success=True,
            clip_path=kwargs["clip_path"],
            target_object_path=kwargs["target_object_path"],
            camera_name=kwargs["camera_name"],
            rendered_camera_name=kwargs["camera_name"],
            motion_summary=AnimationPreviewMotionSummary(is_static=False),
            recommended_interpretation="Ready for review.",
        )

    monkeypatch.setattr("backend.tools.animation.inspector.inspect_animation_clip", mock_inspect)
    monkeypatch.setattr("backend.tools.animation.humanoid.preview_animation", mock_preview)

    result = await preview_humanoid_retarget(
        target_object_path="GenericCharacter",
        clip_path="Assets/Mocap/Walk.anim",
    )

    assert result.success is True
    assert result.is_compatible is False
    assert result.target_avatar_type == "generic"
    assert any("does not have a valid Humanoid Avatar" in issue for issue in result.detected_retarget_issues)
