from typing import Any

import pytest

from backend.schemas import (
    EditorStateResult,
    PlayModeManagementResult,
    RestoreSceneResult,
    SafeTransactionResult,
    SaveSceneResult,
    WaitForEditorIdleResult,
)
from backend.tools import scene


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeBridge:
    def __init__(
        self,
        editor_state: dict[str, Any] | Exception | None = None,
        execute_responses: list[dict[str, Any]] | None = None,
        save_response: dict[str, Any] | None = None,
    ) -> None:
        self.editor_state: dict[str, Any] | Exception = editor_state or {
            "isPlaying": False,
            "isCompiling": False,
            "isUpdating": False,
        }
        self.execute_responses = list(execute_responses or [])
        self.save_response = save_response or {"success": True}
        self.executed_codes: list[str] = []
        self.play_mode_calls: list[bool] = []
        self.save_scene_called = 0

    async def get_editor_state(self) -> dict[str, Any]:
        if isinstance(self.editor_state, Exception):
            raise self.editor_state
        return self.editor_state

    async def execute_code(self, code: str) -> dict[str, Any]:
        self.executed_codes.append(code)
        if self.execute_responses:
            resp = self.execute_responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return {"success": True, "result": {}}

    async def set_play_mode(self, active: bool) -> dict[str, Any]:
        self.play_mode_calls.append(active)
        if isinstance(self.editor_state, dict):
            self.editor_state["isPlaying"] = active
        return {"success": True, "isPlaying": active}

    async def save_scene(self) -> dict[str, Any]:
        self.save_scene_called += 1
        if isinstance(self.save_response, Exception):
            raise self.save_response
        return self.save_response


async def _instant_sleep(_: float) -> None:
    pass


@pytest.mark.anyio
async def test_get_editor_state_with_scene_details(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            {
                "success": True,
                "result": {
                    "sceneName": "SampleScene",
                    "scenePath": "Assets/Scenes/SampleScene.unity",
                    "isDirty": True,
                    "sceneCount": 1,
                    "isPlaying": False,
                    "isPaused": False,
                    "isCompiling": False,
                    "isUpdating": False,
                },
            }
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.get_editor_state(include_scene_details=True)

    assert isinstance(result, EditorStateResult)
    assert result.success is True
    assert result.is_idle is True
    assert result.is_playing is False
    assert result.active_scene_name == "SampleScene"
    assert result.active_scene_path == "Assets/Scenes/SampleScene.unity"
    assert result.active_scene_dirty is True
    assert result.loaded_scene_count == 1


@pytest.mark.anyio
async def test_get_editor_state_compiling_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": True, "isCompiling": True, "isUpdating": True},
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.get_editor_state(include_scene_details=False)

    assert result.success is True
    assert result.is_idle is False
    assert result.is_compiling is True
    assert result.is_updating is True
    assert result.is_playing is True
    assert any("compiling" in w for w in result.warnings)
    assert any("updating" in w for w in result.warnings)
    assert any("Play Mode" in w for w in result.warnings)


@pytest.mark.anyio
async def test_get_editor_state_bridge_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge()
    fake_bridge.editor_state = ConnectionError("Bridge unreachable")
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.get_editor_state()

    assert result.success is False
    assert "Bridge unreachable" in (result.error or "")
    assert result.is_idle is False


@pytest.mark.anyio
async def test_wait_for_editor_idle_immediate(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.wait_for_editor_idle(timeout_seconds=5.0)

    assert isinstance(result, WaitForEditorIdleResult)
    assert result.success is True
    assert result.is_idle is True
    assert result.message == "Unity Editor is idle."


@pytest.mark.anyio
async def test_wait_for_editor_idle_after_compilation(monkeypatch: pytest.MonkeyPatch) -> None:
    states = [
        {"isPlaying": False, "isCompiling": True, "isUpdating": False},
        {"isPlaying": False, "isCompiling": False, "isUpdating": False},
    ]

    class PollingBridge:
        def __init__(self) -> None:
            self.calls = 0

        async def get_editor_state(self) -> dict[str, Any]:
            state = states[min(self.calls, len(states) - 1)]
            self.calls += 1
            return state

    fake_bridge = PollingBridge()
    monkeypatch.setattr(scene, "bridge", fake_bridge)
    monkeypatch.setattr(scene, "_sleep", _instant_sleep)

    result = await scene.wait_for_editor_idle(timeout_seconds=5.0, poll_interval_seconds=0.01)

    assert result.success is True
    assert result.is_idle is True
    assert fake_bridge.calls >= 2


@pytest.mark.anyio
async def test_wait_for_editor_idle_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": True, "isUpdating": False},
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)
    monkeypatch.setattr(scene, "_sleep", _instant_sleep)

    result = await scene.wait_for_editor_idle(timeout_seconds=0.001, poll_interval_seconds=0.001)

    assert result.success is False
    assert result.is_idle is False
    assert "Timed out" in (result.error or "")


@pytest.mark.anyio
async def test_playmode_management_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.playmode_management(play=True, wait_for_idle=False)

    assert isinstance(result, PlayModeManagementResult)
    assert result.success is True
    assert result.is_playing is True
    assert result.previous_state is False
    assert fake_bridge.play_mode_calls == [True]


@pytest.mark.anyio
async def test_save_scene_in_edit_mode_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            {
                "success": True,
                "result": {
                    "sceneName": "MainScene",
                    "scenePath": "Assets/MainScene.unity",
                    "wasDirty": True,
                    "saved": True,
                },
            }
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.save_scene()

    assert isinstance(result, SaveSceneResult)
    assert result.success is True
    assert result.is_saved is True
    assert result.scene_name == "MainScene"
    assert result.scene_path == "Assets/MainScene.unity"
    assert result.was_dirty is True


@pytest.mark.anyio
async def test_save_scene_blocked_in_play_mode_for_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": True, "isCompiling": False, "isUpdating": False},
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.save_scene(force_during_play_mode=False)

    assert result.success is False
    assert result.is_saved is False
    assert "corrupt" in (result.error or "").lower()
    assert any("Play Mode" in w for w in result.warnings)


@pytest.mark.anyio
async def test_save_scene_forced_in_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": True, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            {
                "success": True,
                "result": {
                    "sceneName": "PlayScene",
                    "scenePath": "Assets/PlayScene.unity",
                    "wasDirty": True,
                    "saved": True,
                },
            }
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.save_scene(force_during_play_mode=True)

    assert result.success is True
    assert result.is_saved is True
    assert any("Force saved" in w for w in result.warnings)


@pytest.mark.anyio
async def test_save_scene_blocked_during_compilation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": True, "isUpdating": False},
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.save_scene()

    assert result.success is False
    assert "compiling" in (result.error or "").lower()


@pytest.mark.anyio
async def test_safe_transaction_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            # 1. Undo group start
            {"success": True, "result": {"undoGroup": 42}},
            # 2. Main code execution
            {"success": True, "result": {"spawned": "GameObject_1"}, "logs": ["Spawned GameObject_1"]},
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.safe_transaction(
        editor_code="var go = new GameObject();",
        auto_save=False,
        record_undo=True,
    )

    assert isinstance(result, SafeTransactionResult)
    assert result.success is True
    assert result.undo_group == 42
    assert result.rolled_back is False
    assert result.execution_result == {"spawned": "GameObject_1"}
    assert result.logs == ["Spawned GameObject_1"]


@pytest.mark.anyio
async def test_safe_transaction_failure_auto_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            # 1. Undo group start
            {"success": True, "result": {"undoGroup": 105}},
            # 2. Main code execution (fails)
            {"success": False, "error": "NullReferenceException in user script"},
            # 3. Rollback execution
            {"success": True, "result": {"reverted": True}},
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.safe_transaction(
        editor_code="throw new System.NullReferenceException();",
        restore_on_failure=True,
        record_undo=True,
    )

    assert result.success is False
    assert result.rolled_back is True
    assert result.undo_group == 105
    assert "NullReferenceException" in (result.error or "")
    assert "rolled back" in result.message


@pytest.mark.anyio
async def test_safe_transaction_auto_save_in_edit_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            # Pre-save (via C#)
            {"success": True, "result": {"saved": True, "wasDirty": False, "sceneName": "S"}},
            # Undo group
            {"success": True, "result": {"undoGroup": 1}},
            # Code exec
            {"success": True, "result": {"done": True}},
            # Post-save (via C#)
            {"success": True, "result": {"saved": True, "wasDirty": False, "sceneName": "S"}},
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.safe_transaction(
        editor_code="return null;",
        auto_save=True,
    )

    assert result.success is True
    assert result.scene_saved is True


@pytest.mark.anyio
async def test_safe_transaction_in_play_mode_skips_autosave(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": True, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            # Undo group
            {"success": True, "result": {"undoGroup": 2}},
            # Code exec
            {"success": True, "result": {"done": True}},
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.safe_transaction(
        editor_code="return null;",
        auto_save=True,
    )

    assert result.success is True
    assert result.scene_saved is False
    assert any("Play Mode" in w for w in result.warnings)


@pytest.mark.anyio
async def test_restore_scene_state_undo_revert(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        execute_responses=[
            {"success": True, "result": {"reverted": True, "undoGroup": 42}},
        ]
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.restore_scene_state(undo_group=42)

    assert isinstance(result, RestoreSceneResult)
    assert result.success is True
    assert result.reverted_undo is True
    assert result.reloaded_scene is False


@pytest.mark.anyio
async def test_restore_scene_state_reload_active_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": False, "isCompiling": False, "isUpdating": False},
        execute_responses=[
            {
                "success": True,
                "result": {"reloaded": True, "sceneName": "ReloadedScene", "scenePath": "Assets/S.unity"},
            },
        ],
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.restore_scene_state(reload_active_scene=True)

    assert result.success is True
    assert result.reloaded_scene is True
    assert result.active_scene_name == "ReloadedScene"


@pytest.mark.anyio
async def test_restore_scene_state_reload_blocked_in_playmode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        editor_state={"isPlaying": True, "isCompiling": False, "isUpdating": False},
    )
    monkeypatch.setattr(scene, "bridge", fake_bridge)

    result = await scene.restore_scene_state(reload_active_scene=True)

    assert result.success is False
    assert result.reloaded_scene is False
    assert "Play Mode" in (result.error or "")


@pytest.mark.anyio
async def test_restore_scene_state_no_action_requested() -> None:
    result = await scene.restore_scene_state(undo_group=None, reload_active_scene=False)

    assert result.success is False
    assert "No restore action" in (result.error or "")
