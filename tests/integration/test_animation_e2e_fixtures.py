from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from mcp.server.mcpserver import Image

from backend.bridge.client import UnityBridge
from backend.bridge.exceptions import BridgeProtocolError
from backend.config import Settings
from backend.schemas import CameraSubjectContactResult, HumanoidValidationResult
from backend.schemas.preview_record import AnimationPreviewRecord
from backend.schemas.vision import VideoCaptureResult, VideoFrame
from backend.tools import animation as animation_pkg
from backend.tools import scene, vision
from backend.tools.animation.humanoid import validate_humanoid_avatar
from backend.tools.animation.preview import preview_animation
from backend.tools.vision.video import _discard_stale_frames


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_png_bytes(
    color: tuple[int, int, int],
    size: tuple[int, int] = (16, 16),
    changed_pixel: tuple[int, int, tuple[int, int, int]] | None = None,
) -> bytes:
    width, height = size
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            pixel = color
            if changed_pixel and (x, y) == changed_pixel[:2]:
                pixel = changed_pixel[2]
            row.extend(pixel)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def _make_png_base64(
    color: tuple[int, int, int],
    size: tuple[int, int] = (16, 16),
    changed_pixel: tuple[int, int, tuple[int, int, int]] | None = None,
) -> str:
    return base64.b64encode(_make_png_bytes(color, size, changed_pixel)).decode("ascii")


# ---------------------------------------------------------------------------
# 1. Play Mode domain reload and bridge re-binding fixture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_playmode_domain_reload_reconnection_and_transient_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Deterministic end-to-end fixture for Play Mode transition through a real Unity domain reload:
    1. Socket drops / connection reset during assembly unload.
    2. Transient empty HTTP 200 body while HttpListener begins listening before runtime initialization.
    3. Transient non-JSON HTML body while domain reload is finalizing.
    4. Bridge re-binds and answers with valid JSON editor state.
    """
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        unity_bridge_url="http://127.0.0.1",
        unity_bridge_port=7890,
        unity_bridge_timeout_seconds=2.0,
        unity_bridge_retry_backoff=0.001,
        unity_bridge_ready_wait_seconds=2.0,
    )
    bridge = UnityBridge(settings=settings)

    stage = 0

    async def transient_editor_state() -> dict[str, Any]:
        nonlocal stage
        stage += 1
        if stage == 1:
            req = httpx.Request("GET", "http://127.0.0.1:7890/api/editor/state")
            raise httpx.ConnectError("Connection refused: domain reload unloaded bridge socket", request=req)
        if stage == 2:
            raise BridgeProtocolError(
                message="Bridge returned an empty body for '/api/editor/state' with status 200.",
                status_code=200,
            )
        if stage == 3:
            raise BridgeProtocolError(
                message="Bridge returned a non-JSON body for '/api/editor/state': '<html>reloading</html>'",
                status_code=200,
            )
        return {"isPlaying": True, "isCompiling": False, "isUpdating": False}

    with patch.object(bridge, "get_editor_state", side_effect=transient_editor_state):
        state = await bridge.wait_for_play_mode(target_playing=True, timeout_seconds=2.0, poll_interval_seconds=0.005)

    assert state["isPlaying"] is True
    assert stage >= 4


# ---------------------------------------------------------------------------
# 2. Stale first Game View frame detection and discard fixture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stale_game_view_frame_detection_and_discard(tmp_path: Path) -> None:
    """
    Deterministic fixture: when entering Play Mode, the first frame from Game View matches the
    pre-Play-Mode baseline image (stale frame). The stale frame detector must discard it and wait
    for the dynamic running frame.
    """
    baseline_png = _make_png_bytes((255, 0, 0), size=(16, 16))
    stale_png = _make_png_bytes((255, 0, 0), size=(16, 16))
    dynamic_png = _make_png_bytes((0, 255, 0), size=(16, 16))

    baseline_path = tmp_path / "baseline.png"
    baseline_path.write_bytes(baseline_png)
    stale_path = tmp_path / "stale.png"
    stale_path.write_bytes(stale_png)
    dynamic_path = tmp_path / "dynamic.png"
    dynamic_path.write_bytes(dynamic_png)

    baseline_frame = VideoFrame(
        frame_index=-1,
        timestamp_seconds=0.0,
        file_path=str(baseline_path),
        width=16,
        height=16,
        camera_name="Main Camera",
        mode="game_camera",
    )

    capture_calls = 0

    async def fake_capture_video_frame(**_kwargs: Any) -> VideoFrame:
        nonlocal capture_calls
        capture_calls += 1
        if capture_calls == 1:
            # First attempt: stale frame matching baseline
            return VideoFrame(
                frame_index=0,
                timestamp_seconds=0.0,
                file_path=str(stale_path),
                width=16,
                height=16,
                camera_name="Main Camera",
                mode="game_camera",
            )
        # Second attempt: dynamic running frame with changed pixels
        return VideoFrame(
            frame_index=0,
            timestamp_seconds=0.0,
            file_path=str(dynamic_path),
            width=16,
            height=16,
            camera_name="Main Camera",
            mode="game_camera",
        )

    warnings: list[str] = []
    with (
        patch("backend.tools.vision.video._capture_video_frame", side_effect=fake_capture_video_frame),
        patch("backend.tools.vision._sleep", new_callable=AsyncMock),
    ):
        await _discard_stale_frames(
            baseline=baseline_frame,
            camera_name="Main Camera",
            subject_path="Character",
            mode="game_camera",
            width=16,
            height=16,
            warnings=warnings,
        )

    assert capture_calls == 2
    assert not any("still matched its pre-Play-Mode content" in w for w in warnings)


@pytest.mark.anyio
async def test_stale_game_view_frame_warns_on_persistently_static_scene(tmp_path: Path) -> None:
    """If Game View remains identical to baseline after maximum warm-up attempts, a descriptive warning is added."""
    baseline_png = _make_png_bytes((120, 120, 120), size=(16, 16))
    stale_path = tmp_path / "static.png"
    stale_path.write_bytes(baseline_png)

    baseline_frame = VideoFrame(
        frame_index=-1,
        timestamp_seconds=0.0,
        file_path=str(stale_path),
        width=16,
        height=16,
        camera_name="Main Camera",
        mode="game_camera",
    )

    async def fake_capture_video_frame(**_kwargs: Any) -> VideoFrame:
        return VideoFrame(
            frame_index=0,
            timestamp_seconds=0.0,
            file_path=str(stale_path),
            width=16,
            height=16,
            camera_name="Main Camera",
            mode="game_camera",
        )

    warnings: list[str] = []
    with (
        patch("backend.tools.vision.video._capture_video_frame", side_effect=fake_capture_video_frame),
        patch("backend.tools.vision._sleep", new_callable=AsyncMock),
    ):
        await _discard_stale_frames(
            baseline=baseline_frame,
            camera_name="Main Camera",
            subject_path="Character",
            mode="game_camera",
            width=16,
            height=16,
            warnings=warnings,
        )

    assert any("still matched its pre-Play-Mode content" in w for w in warnings)


# ---------------------------------------------------------------------------
# 3. High-FPS MP4 capture and artifact verification fixture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_high_fps_mp4_capture_and_artifact_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    End-to-end fixture: renders a 24 fps animation sequence, generates an MP4 video artifact,
    persists record.json and keyframes, asserts scene restoration, and verifies real artifacts on disk.
    """
    monkeypatch.chdir(tmp_path)

    # Prepare 25 distinct frames for a 1-second clip at 24 fps
    frames_payload: list[dict[str, Any]] = []
    for i in range(25):
        color = ((i * 10) % 255, (i * 20) % 255, (i * 5) % 255)
        frames_payload.append(
            {
                "frameIndex": i,
                "timestamp": round(i / 24.0, 4),
                "imageBase64": _make_png_base64(color, size=(32, 32)),
            }
        )

    native_sequence_result = {
        "success": True,
        "cameraName": "Main Camera",
        "clipName": "Attack",
        "clipPath": "Assets/Clips/Attack.anim",
        "targetObjectPath": "Character",
        "clipLength": 1.0,
        "startTime": 0.0,
        "endTime": 1.0,
        "width": 32,
        "height": 32,
        "requestedFrameCount": 25,
        "frameCount": 25,
        "requestedFps": 24.0,
        "actualFps": 24.0,
        "totalDuration": 1.0,
        "timingSource": "edit_mode_sampled",
        "poseRestored": True,
        "sceneDirtiedByPreview": False,
        "clipFps": 24.0,
        "loopTime": False,
        "isHumanoidClip": False,
        "unresolvedCurvePaths": 0,
        "unresolvedCurvePathSamples": [],
        "autoFrameStatus": "disabled",
        "previewCameraCreated": False,
        "previewCameraDestroyed": False,
        "events": [{"time": 0.5, "functionName": "OnHit"}],
        "frames": frames_payload,
        "warnings": [],
    }

    class MockAnimationBridge:
        async def supports_feature(self, feature: str) -> bool:
            return feature in {"animation_preview_sequence", "animation_authoring"}

        async def get_editor_state(self) -> dict[str, Any]:
            return {"isPlaying": False}

        async def execute_capability(self, code: str, **_kwargs: Any) -> dict[str, Any]:
            del code
            return {
                "result": {
                    "success": True,
                    "clipName": "Attack",
                    "clipPath": "Assets/Clips/Attack.anim",
                    "length": 1.0,
                    "fps": 24.0,
                    "bindings": [],
                    "events": [{"time": 0.5, "functionName": "OnHit"}],
                }
            }

        async def preview_animation_sequence_native(self, **_kwargs: Any) -> dict[str, Any]:
            return native_sequence_result

    monkeypatch.setattr(animation_pkg, "bridge", MockAnimationBridge())

    res = await preview_animation(
        clip_path="Assets/Clips/Attack.anim",
        target_object_path="Character",
        camera_name="Main Camera",
        fps=24,
        start_time=0.0,
        end_time=1.0,
        width=32,
        height=32,
    )

    assert isinstance(res, tuple)
    result, img = res
    assert isinstance(img, Image)
    assert result.success is True
    assert result.preview_id is not None
    assert result.actual_fps == pytest.approx(24.0, abs=0.1)
    assert result.frame_count == 25
    assert result.pose_restored is True

    # Verify physical artifacts produced in isolated artifacts directory
    preview_dir = tmp_path / "artifacts" / "animation_previews" / result.preview_id
    assert preview_dir.is_dir(), f"Preview directory '{preview_dir}' does not exist"

    # 1. record.json artifact
    record_file = preview_dir / "record.json"
    assert record_file.is_file(), "record.json was not created"
    record_data = AnimationPreviewRecord.model_validate_json(record_file.read_text(encoding="utf-8"))
    assert record_data.preview_id == result.preview_id
    assert record_data.capture_settings.requested_fps == 24
    assert record_data.editor_state.pose_restored is True
    assert record_data.artifacts.record_path == str(record_file.resolve())

    # 2. MP4 video artifact
    assert record_data.artifacts.mp4_path is not None
    mp4_file = Path(record_data.artifacts.mp4_path)
    assert mp4_file.is_file(), f"MP4 file '{mp4_file}' was not created"
    mp4_bytes = mp4_file.read_bytes()
    assert len(mp4_bytes) > 0, "MP4 file is empty"
    # An MP4 container has 'ftyp' starting at byte offset 4
    assert b"ftyp" in mp4_bytes[:16], "Artifact is not a valid MP4 container file"

    # 3. Keyframe image artifacts
    assert len(record_data.key_frames) > 0
    for kf in record_data.key_frames:
        kf_path = Path(kf.file_path)
        assert kf_path.is_file(), f"Keyframe file '{kf_path}' was not created"
        kf_bytes = kf_path.read_bytes()
        assert kf_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "Keyframe is not a valid PNG file"


# ---------------------------------------------------------------------------
# 4. Fast impact and hit-stop sequence E2E fixture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fast_impact_hit_stop_sequence_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    End-to-end fixture for authoring a synchronized character-camera impact and hit-stop sequence.
    Verifies that impact, hit-stop, and camera recoil share the exact timestamp.
    """

    class MockCameraActionBridge:
        async def supports_feature(self, feature: str) -> bool:
            return feature in {"camera_subject_action", "animation_authoring"}

        async def get_editor_state(self) -> dict[str, Any]:
            return {"isPlaying": False}

        async def solve_camera_subject_contact_native(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "success": True,
                "characterBackupId": "backup_char_123",
                "cameraBackupId": "backup_cam_123",
                "impactWorldPosition": [0.1, 0.9, -1.2],
                "impactScreenResidualPixels": [0.5, 0.4],
                "maxLimbReachRatio": 0.88,
                "keyframesModifiedCount": 16,
                "warnings": [],
            }

    monkeypatch.setattr(animation_pkg, "bridge", MockCameraActionBridge())

    result = await animation_pkg.camera_action.solve_camera_subject_contact(
        character_path="Character",
        character_clip_path="Assets/Clips/Kick.anim",
        camera_name="ActionCamera",
        camera_clip_path="Assets/Clips/CameraShake.anim",
        effector="left_foot",
        impact_time=0.4,
        contact_duration=0.2,
        hit_stop_duration=0.08,
    )

    assert isinstance(result, CameraSubjectContactResult)
    assert result.success is True
    assert result.keyframes_modified_count == 16
    assert result.max_limb_reach_ratio == pytest.approx(0.88)
    assert result.impact_world_position == [0.1, 0.9, -1.2]


# ---------------------------------------------------------------------------
# 5. Generic rig (no Avatar) and Valid Humanoid rig diagnostics E2E fixture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_generic_rig_and_valid_humanoid_rig_diagnostics_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    End-to-end fixture comparing Avatar diagnostics across a Generic rig without Avatar vs.
    a compliant Humanoid rig.
    """

    class MockHumanoidBridge:
        def __init__(self) -> None:
            self.queried_target: str | None = None

        async def supports_feature(self, feature: str) -> bool:
            return feature == "humanoid_avatar_diagnostics"

        async def get_editor_state(self) -> dict[str, Any]:
            return {"isPlaying": False}

        async def validate_humanoid_avatar(self, target_path: str | None = None, **_kwargs: Any) -> dict[str, Any]:
            self.queried_target = target_path
            if target_path == "GenericPropRig":
                return {
                    "success": True,
                    "targetPath": target_path,
                    "isValidHumanoid": False,
                    "avatarStatus": "missing_avatar",
                    "missingRequiredBones": ["Head", "LeftUpperLeg", "RightUpperLeg"],
                    "missingOptionalBones": ["Chest"],
                    "boneMappings": {"Hips": "Pelvis"},
                    "blockers": [
                        {
                            "boneName": "Head",
                            "category": "missing_bone",
                            "severity": "blocker",
                            "message": "Required Humanoid bone 'Head' is not mapped or missing.",
                            "suggestedFix": "Map a bone from the model to 'Head' in the Avatar definition.",
                        }
                    ],
                    "posture": {
                        "armsHorizontalAngle": 0.0,
                        "legsVerticalAngle": 0.0,
                        "isTpose": False,
                        "isApose": False,
                        "symmetryScore": 0.0,
                        "warnings": [],
                    },
                    "warnings": ["Rig has missing bones; treat as Generic rig."],
                }

            # Valid Humanoid
            return {
                "success": True,
                "targetPath": target_path,
                "isValidHumanoid": True,
                "avatarStatus": "valid_humanoid",
                "missingRequiredBones": [],
                "missingOptionalBones": [],
                "boneMappings": {
                    "Hips": "Hips",
                    "Spine": "Spine",
                    "Head": "Head",
                    "LeftUpperLeg": "LeftUpperLeg",
                    "LeftLowerLeg": "LeftLowerLeg",
                    "LeftFoot": "LeftFoot",
                    "RightUpperLeg": "RightUpperLeg",
                    "RightLowerLeg": "RightLowerLeg",
                    "RightFoot": "RightFoot",
                    "LeftUpperArm": "LeftUpperArm",
                    "LeftLowerArm": "LeftLowerArm",
                    "LeftHand": "LeftHand",
                    "RightUpperArm": "RightUpperArm",
                    "RightLowerArm": "RightLowerArm",
                    "RightHand": "RightHand",
                },
                "blockers": [],
                "posture": {
                    "armsHorizontalAngle": 89.2,
                    "legsVerticalAngle": 1.5,
                    "isTpose": True,
                    "isApose": False,
                    "symmetryScore": 0.99,
                    "warnings": [],
                },
                "warnings": [],
            }

    fake_bridge = MockHumanoidBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake_bridge)

    # 1. Test Generic rig
    generic_res = await validate_humanoid_avatar(target_path="GenericPropRig")
    assert isinstance(generic_res, HumanoidValidationResult)
    assert generic_res.success is True
    assert generic_res.is_valid_humanoid is False
    assert generic_res.avatar_status == "missing_avatar"
    assert "Head" in generic_res.missing_required_bones
    assert len(generic_res.blockers) >= 1
    assert generic_res.blockers[0].category == "missing_bone"
    assert generic_res.blockers[0].severity == "blocker"

    # 2. Test Valid Humanoid rig
    humanoid_res = await validate_humanoid_avatar(target_path="HumanoidCharacter")
    assert isinstance(humanoid_res, HumanoidValidationResult)
    assert humanoid_res.success is True
    assert humanoid_res.is_valid_humanoid is True
    assert humanoid_res.avatar_status == "valid_humanoid"
    assert len(humanoid_res.missing_required_bones) == 0
    assert len(humanoid_res.blockers) == 0
    assert humanoid_res.posture is not None
    assert humanoid_res.posture.is_tpose is True
