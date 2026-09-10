import inspect
import types
from typing import Any, Union, get_args, get_origin, get_type_hints

import pytest

from backend.bridge import BridgeError
from backend.schemas.base import BaseToolResult

# Import tools to ensure registration
from backend.tools import animation, asset, bridge, mesh, prefab, scene, vision

TOOL_FUNCTIONS = [
    # Bridge & Queue
    bridge.health.get_bridge_status,
    bridge.queue.check_ticket_status,
    # Scene
    scene.state.get_editor_state,
    scene.lifecycle.playmode_management,
    scene.lifecycle.save_scene,
    scene.execution.safe_transaction,
    scene.execution.restore_scene_state,
    # Vision
    vision.capture.screenshot,
    vision.capture.compare_screenshots,
    vision.capture.inspect_scene_visual,
    vision.camera.list_scene_cameras,
    vision.camera.project_world_points,
    vision.camera.diagnose_camera_framing,
    vision.video.capture_video,
    # Animation & Skeleton
    animation.inspector.inspect_animation_clip,
    animation.sampling.sample_animation_clip,
    animation.skeleton.skeleton_mapper,
    animation.skeleton.find_bones,
    animation.preview.preview_animation,
    animation.records.get_animation_preview_record,
    animation.records.list_animation_preview_records,
    animation.authoring.list_animation_keyframes,
    animation.backups.list_animation_backups,
    animation.backups.restore_animation_clip,
    animation.camera_action.solve_camera_subject_contact,
    animation.contact.analyze_contact_constraints,
    animation.contact.bake_contact_constraints,
    animation.contact_bake.bake_effector_contact,
    animation.gaze.solve_character_gaze,
    animation.humanoid.validate_humanoid_avatar,
    animation.humanoid.configure_humanoid_avatar,
    animation.ik.solve_two_bone_ik,
    animation.ik.place_effector_in_viewport,
    animation.intersections.analyze_self_intersections,
    animation.qa.analyze_joint_motion,
    animation.qa.detect_curve_discontinuities,
    animation.transaction.edit_animation_transaction,
    # Mesh
    mesh.diagnostics.skinned_mesh_diagnostics,
    # Asset Web Search & Auto-Download
    asset.search_assets,
    asset.download_and_import_asset,
    asset.import_local_asset,
    asset.inspect_imported_asset,
    asset.instantiate_scene_asset,
    # Prefab assets
    prefab.inspect_prefab_asset,
]


def _extract_base_tool_result_subclasses(annotation: Any) -> list[type[BaseToolResult]]:
    origin = get_origin(annotation)
    if origin in (types.UnionType, Union):
        results: list[type[BaseToolResult]] = []
        for arg in get_args(annotation):
            results.extend(_extract_base_tool_result_subclasses(arg))
        return results
    if origin is tuple:
        args = get_args(annotation)
        if args:
            return _extract_base_tool_result_subclasses(args[0])
    if isinstance(annotation, type) and issubclass(annotation, BaseToolResult):
        return [annotation]
    return []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("tool_fn", TOOL_FUNCTIONS)
def test_tool_return_type_is_base_tool_result_subclass(tool_fn: Any) -> None:
    """Every Visora tool must explicitly declare a return type inheriting from BaseToolResult (or tuple containing it)."""
    hints = get_type_hints(tool_fn)
    return_type = hints.get("return")
    assert return_type is not None, f"Tool {tool_fn.__name__} has no return type annotation"
    result_classes = _extract_base_tool_result_subclasses(return_type)
    assert result_classes, (
        f"Tool {tool_fn.__name__} returns {return_type}, which does not inherit from or contain BaseToolResult"
    )


@pytest.mark.parametrize("tool_fn", TOOL_FUNCTIONS)
def test_tool_has_structured_docstring(tool_fn: Any) -> None:
    """Every tool must have a clear docstring documenting arguments and structured return output."""
    doc = inspect.getdoc(tool_fn)
    assert doc is not None, f"Tool {tool_fn.__name__} is missing a docstring"
    assert len(doc.strip()) > 20, f"Tool {tool_fn.__name__} docstring is too short"
    assert "Returns:" in doc or "Result" in doc or "diagnostic" in doc.lower(), (
        f"Tool {tool_fn.__name__} docstring should document return value schema"
    )


class FailingBridge:
    """Mock bridge that raises BridgeError on any operation."""

    base_url = "http://localhost:7890"

    async def execute_code(self, _code: str) -> dict[str, Any]:
        raise BridgeError("Bridge connection refused")

    async def render_camera(
        self, _code: str, _camera_name: str, _width: int, _height: int, _image_format: str = "PNG"
    ) -> dict[str, Any]:
        raise BridgeError("Bridge connection refused")

    async def execute_capability(
        self,
        _code: str,
        *,
        native_path: str | None = None,
        native_payload: dict[str, Any] | None = None,
        retry_on_timeout: bool = True,
    ) -> dict[str, Any]:
        del native_path, native_payload, retry_on_timeout
        raise BridgeError("Bridge connection refused")

    async def get_editor_state(self) -> dict[str, Any]:
        raise BridgeError("Bridge connection refused")

    async def supports_feature(self, _feature: str) -> bool:
        raise BridgeError("Bridge connection refused")

    async def wait_for_editor_ready(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        del timeout_seconds
        raise BridgeError("Bridge connection refused")

    async def scan_available_ports(self) -> list[dict[str, Any]]:
        raise BridgeError("Bridge connection refused")

    async def ping(self) -> tuple[bool, float | None]:
        return False, None

    async def get_queue_status(self, _ticket_id: str) -> dict[str, Any]:
        raise BridgeError("Bridge connection refused")

    async def set_play_mode(self, _active: bool) -> dict[str, Any]:
        raise BridgeError("Bridge connection refused")

    async def save_scene(self) -> dict[str, Any]:
        raise BridgeError("Bridge connection refused")


class ErrorResponseBridge:
    """Mock bridge that returns Unity execution failure payloads."""

    base_url = "http://localhost:7890"

    async def execute_code(self, _code: str) -> dict[str, Any]:
        return {"success": False, "error": "Unity C# compilation or runtime error"}

    async def render_camera(
        self, _code: str, _camera_name: str, _width: int, _height: int, _image_format: str = "PNG"
    ) -> dict[str, Any]:
        return {"success": False, "error": "Unity C# compilation or runtime error"}

    async def execute_capability(
        self,
        _code: str,
        *,
        native_path: str | None = None,
        native_payload: dict[str, Any] | None = None,
        retry_on_timeout: bool = True,
    ) -> dict[str, Any]:
        del native_path, native_payload, retry_on_timeout
        return {"success": False, "error": "Unity C# compilation or runtime error"}

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": False, "isCompiling": False}

    async def supports_feature(self, feature: str) -> bool:
        # Only the native-only prefab capability is advertised here; every other tool keeps taking
        # the same path through this mock as before, so their assertions stay about Unity errors.
        return feature == "prefab_asset_inspection"

    async def wait_for_editor_ready(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        del timeout_seconds
        return {"isPlaying": False, "isCompiling": False}

    async def inspect_prefab_asset_native(self, **_kwargs: Any) -> dict[str, Any]:
        return {"success": False, "error": "Unity C# compilation or runtime error"}

    async def scan_available_ports(self) -> list[dict[str, Any]]:
        return [{"port": 7890, "is_open": True, "latency_ms": 1.2}]

    async def ping(self) -> tuple[bool, float | None]:
        return True, 1.2

    async def get_active_port(self) -> int:
        return 7890

    async def get_queue_status(self, _ticket_id: str) -> dict[str, Any]:
        return {"status": "failed", "error": "Unity C# compilation or runtime error"}

    async def set_play_mode(self, _active: bool) -> dict[str, Any]:
        return {"success": False, "error": "Failed to set play mode"}

    async def save_scene(self) -> dict[str, Any]:
        return {"success": False, "error": "Failed to save scene"}


@pytest.mark.anyio
async def test_all_tools_gracefully_handle_bridge_outage(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: PLR0915
    """Verifies that all async tools return success=False and structured error info when the bridge fails."""
    failing_bridge = FailingBridge()

    monkeypatch.setattr(bridge.health, "bridge", failing_bridge)
    monkeypatch.setattr(bridge.queue, "bridge", failing_bridge)
    monkeypatch.setattr(scene, "bridge", failing_bridge)
    monkeypatch.setattr(vision, "bridge", failing_bridge)
    monkeypatch.setattr(animation, "bridge", failing_bridge)
    monkeypatch.setattr(mesh, "bridge", failing_bridge)
    monkeypatch.setattr(prefab, "bridge", failing_bridge)

    raw_res: Any
    res: BaseToolResult

    # 1. get_bridge_status
    res = await bridge.health.get_bridge_status(scan_all_ports=False)
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 2. check_ticket_status
    res = await bridge.queue.check_ticket_status("ticket-1")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 3. get_editor_state
    res = await scene.state.get_editor_state()
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 4. playmode_management
    res = await scene.lifecycle.playmode_management(play=True, wait_for_idle=False)
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 5. save_scene
    res = await scene.lifecycle.save_scene()
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 6. safe_transaction
    res = await scene.execution.safe_transaction("Debug.Log(1);")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 7. restore_scene_state
    res = await scene.execution.restore_scene_state(undo_group=1)
    assert isinstance(res, BaseToolResult)
    assert res.success is False

    # 8. screenshot
    raw_res = await vision.capture.screenshot()
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 9. list_scene_cameras
    res = await vision.camera.list_scene_cameras()
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 10. project_world_points
    res = await vision.camera.project_world_points([[0, 0, 1]])
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 11. diagnose_camera_framing
    res = await vision.camera.diagnose_camera_framing("Player")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 12. inspect_animation_clip
    res = await animation.inspector.inspect_animation_clip("Assets/Test.anim")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 13. sample_animation_clip
    res = await animation.sampling.sample_animation_clip("Player", "Assets/Test.anim")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 14. skeleton_mapper
    res = await animation.skeleton.skeleton_mapper("Root")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 15. find_bones
    res = await animation.skeleton.find_bones("Root", "Head")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 16. skinned_mesh_diagnostics
    res = await mesh.diagnostics.skinned_mesh_diagnostics("Body")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 17. capture_video (frames)
    raw_res = await vision.video.capture_video(output="frames", duration_seconds=0.1)
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 18. capture_video (mp4)
    raw_res = await vision.video.capture_video(output="mp4", duration_seconds=0.1)
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 20. compare_screenshots
    raw_res = vision.capture.compare_screenshots(before_image_path="invalid", after_image_path="invalid")
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 21. inspect_scene_visual
    raw_res = await vision.capture.inspect_scene_visual()
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 22. preview_animation
    raw_res = await animation.preview.preview_animation("Player", "Assets/Test.anim")
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None

    # 23. inspect_prefab_asset
    res = await prefab.inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")
    assert isinstance(res, BaseToolResult)
    assert res.success is False
    assert res.error is not None


@pytest.mark.anyio
async def test_all_tools_prevent_fake_success_on_unity_errors(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: PLR0915
    """Verifies that when Unity returns an error payload, tools report success=False rather than fake success."""
    error_bridge = ErrorResponseBridge()

    monkeypatch.setattr(bridge.health, "bridge", error_bridge)
    monkeypatch.setattr(bridge.queue, "bridge", error_bridge)
    monkeypatch.setattr(scene, "bridge", error_bridge)
    monkeypatch.setattr(vision, "bridge", error_bridge)
    monkeypatch.setattr(animation, "bridge", error_bridge)
    monkeypatch.setattr(mesh, "bridge", error_bridge)
    monkeypatch.setattr(prefab, "bridge", error_bridge)

    raw_res: Any
    res: BaseToolResult

    # 1. safe_transaction with error C# code
    res = await scene.execution.safe_transaction("invalid c#")
    assert res.success is False
    assert res.error is not None

    # 2. screenshot with error
    raw_res = await vision.capture.screenshot()
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert res.success is False
    assert res.error is not None

    # 3. list_scene_cameras with error
    res = await vision.camera.list_scene_cameras()
    assert res.success is False
    assert res.error is not None

    # 4. project_world_points with error
    res = await vision.camera.project_world_points([[0, 0, 1]])
    assert res.success is False
    assert res.error is not None

    # 5. diagnose_camera_framing with error
    res = await vision.camera.diagnose_camera_framing("Player")
    assert res.success is False
    assert res.error is not None

    # 6. inspect_animation_clip with error
    res = await animation.inspector.inspect_animation_clip("Assets/Test.anim")
    assert res.success is False
    assert res.error is not None

    # 7. sample_animation_clip with error
    res = await animation.sampling.sample_animation_clip("Player", "Assets/Test.anim")
    assert res.success is False
    assert res.error is not None

    # 9. skeleton_mapper with error
    res = await animation.skeleton.skeleton_mapper("Root")
    assert res.success is False
    assert res.error is not None

    # 10. find_bones with error
    res = await animation.skeleton.find_bones("Root", "Head")
    assert res.success is False
    assert res.error is not None

    # 11. skinned_mesh_diagnostics with error
    res = await mesh.diagnostics.skinned_mesh_diagnostics("Body")
    assert res.success is False
    assert res.error is not None

    # 12. capture_video (frames) with error
    raw_res = await vision.video.capture_video(output="frames", duration_seconds=0.1)
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert res.success is False
    assert res.error is not None

    # 13. capture_video (mp4) with error
    raw_res = await vision.video.capture_video(output="mp4", duration_seconds=0.1)
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert res.success is False
    assert res.error is not None

    # 14. preview_animation with error
    raw_res = await animation.preview.preview_animation("Player", "Assets/Test.anim")
    res = raw_res[0] if isinstance(raw_res, tuple) else raw_res
    assert res.success is False
    assert res.error is not None

    # 15. inspect_prefab_asset with error
    res = await prefab.inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")
    assert res.success is False
    assert res.error is not None
    assert res.hierarchy == []
