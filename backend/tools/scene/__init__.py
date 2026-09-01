import asyncio
import logging
import time
import uuid
from typing import Any, cast

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import (
    EditorStateResult,
    PlayModeManagementResult,
    RestoreSceneResult,
    SafeTransactionResult,
    SaveSceneResult,
    WaitForEditorIdleResult,
)
from backend.tools.scene.scripts import (
    _begin_undo_group_code,
    _get_scene_details_code,
    _reload_scene_code,
    _save_scene_code,
    _undo_transaction_code,
)
from backend.tools.scene.transactions import (
    _execute_undo_rollback,
    _handle_post_transaction_save,
    _handle_pre_transaction_save,
    _register_undo_group,
)

logger = logging.getLogger("backend.tools.scene")
bridge = UnityBridge()


async def _sleep(seconds: float) -> None:
    """Sleep helper to facilitate deterministic testing."""
    await asyncio.sleep(seconds)


@mcp.tool()
async def get_editor_state(include_scene_details: bool = True) -> EditorStateResult:
    """
    Inspects the current Unity Editor state: Play Mode, compilation, active scene and dirty state.

    Args:
        include_scene_details: If True, queries Unity for detailed active scene info (name, path, dirty state).

    Returns:
        An EditorStateResult with comprehensive status flags.
    """
    try:
        raw_state = await bridge.get_editor_state()
        is_playing = bool(raw_state.get("isPlaying", False))
        is_paused = bool(raw_state.get("isPaused", False))
        is_compiling = bool(raw_state.get("isCompiling", False))
        is_updating = bool(raw_state.get("isUpdating", False))
        active_scene_name = cast(str | None, raw_state.get("activeSceneName") or raw_state.get("sceneName"))
        active_scene_path = cast(str | None, raw_state.get("activeScenePath") or raw_state.get("scenePath"))
        active_scene_dirty = cast(bool | None, raw_state.get("isDirty"))
        loaded_scene_count = int(raw_state.get("loadedSceneCount", 1 if active_scene_name else 0))
        warnings: list[str] = []

        if include_scene_details:
            try:
                scene_res = await bridge.execute_code(_get_scene_details_code())
                if scene_res.get("success") and isinstance(scene_res.get("result"), dict):
                    data = cast(dict[str, Any], scene_res["result"])
                    active_scene_name = cast(str | None, data.get("sceneName", active_scene_name))
                    active_scene_path = cast(str | None, data.get("scenePath", active_scene_path))
                    active_scene_dirty = cast(bool | None, data.get("isDirty", active_scene_dirty))
                    loaded_scene_count = int(data.get("sceneCount", loaded_scene_count))
                    is_playing = bool(data.get("isPlaying", is_playing))
                    is_paused = bool(data.get("isPaused", is_paused))
                    is_compiling = bool(data.get("isCompiling", is_compiling))
                    is_updating = bool(data.get("isUpdating", is_updating))
            except Exception as e:
                logger.debug(f"Could not fetch extended scene details via C#: {e}")
                warnings.append(f"Extended scene details query failed: {e}")

        is_idle = not is_compiling and not is_updating

        if is_compiling:
            warnings.append("Unity Editor is currently compiling scripts.")
        if is_updating:
            warnings.append("Unity Editor is currently updating.")
        if is_playing:
            warnings.append("Unity Editor is in Play Mode.")

        return EditorStateResult(
            success=True,
            is_playing=is_playing,
            is_paused=is_paused,
            is_compiling=is_compiling,
            is_updating=is_updating,
            is_idle=is_idle,
            active_scene_name=active_scene_name,
            active_scene_path=active_scene_path,
            active_scene_dirty=active_scene_dirty,
            loaded_scene_count=loaded_scene_count,
            warnings=warnings,
        )
    except Exception as exc:
        logger.exception("get_editor_state failed")
        return EditorStateResult(
            success=False,
            error=str(exc),
            is_idle=False,
            warnings=[f"Failed to communicate with bridge: {exc}"],
        )


@mcp.tool()
async def wait_for_editor_idle(
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.5,
) -> WaitForEditorIdleResult:
    """
    Waits until the Unity Editor reaches an idle state (not compiling scripts and not updating).

    Args:
        timeout_seconds: Maximum duration to wait before returning a timeout error.
        poll_interval_seconds: Seconds between status polls.

    Returns:
        A WaitForEditorIdleResult detailing whether idle was reached.
    """
    start_time = time.time()
    last_state: EditorStateResult | None = None

    try:
        while time.time() - start_time < timeout_seconds:
            last_state = await get_editor_state(include_scene_details=False)
            if last_state.success and last_state.is_idle:
                waited = time.time() - start_time
                return WaitForEditorIdleResult(
                    success=True,
                    is_idle=True,
                    waited_seconds=round(waited, 3),
                    is_compiling=last_state.is_compiling,
                    is_updating=last_state.is_updating,
                    is_playing=last_state.is_playing,
                    warnings=last_state.warnings,
                    message="Unity Editor is idle.",
                )
            await _sleep(poll_interval_seconds)

        waited = time.time() - start_time
        return WaitForEditorIdleResult(
            success=False,
            is_idle=False,
            waited_seconds=round(waited, 3),
            is_compiling=last_state.is_compiling if last_state else False,
            is_updating=last_state.is_updating if last_state else False,
            is_playing=last_state.is_playing if last_state else False,
            error=f"Timed out after {timeout_seconds:.1f}s waiting for Unity Editor idle state.",
            warnings=["Timeout reached while waiting for editor idle."],
            message="Editor did not reach idle state before timeout.",
        )
    except Exception as exc:
        logger.exception("wait_for_editor_idle failed")
        return WaitForEditorIdleResult(
            success=False,
            is_idle=False,
            waited_seconds=round(time.time() - start_time, 3),
            error=str(exc),
            warnings=[f"Error during idle wait: {exc}"],
            message="Error while waiting for editor idle state.",
        )


@mcp.tool()
async def playmode_management(
    play: bool,
    wait_for_idle: bool = True,
    timeout_seconds: float = 30.0,
) -> PlayModeManagementResult:
    """
    Manages the Unity Editor Play Mode state (enter or exit Play Mode safely).

    Args:
        play: Set to True to start play mode, or False to stop and return to edit mode.
        wait_for_idle: If True, waits for editor idle before and after toggling playmode.
        timeout_seconds: Timeout for idle wait operations.

    Returns:
        A PlayModeManagementResult detailing the playmode state change outcome.
    """
    warnings: list[str] = []
    try:
        if wait_for_idle:
            idle_before = await wait_for_editor_idle(timeout_seconds=timeout_seconds)
            if not idle_before.success:
                warnings.append(f"Editor was not idle before play mode change: {idle_before.error}")

        before = await bridge.get_editor_state()
        previous_state = bool(before.get("isPlaying", False))

        await bridge.set_play_mode(play)

        if wait_for_idle:
            idle_after = await wait_for_editor_idle(timeout_seconds=timeout_seconds)
            if not idle_after.success:
                warnings.append(f"Editor was not idle after play mode change: {idle_after.error}")

        after = await bridge.get_editor_state()
        is_playing = bool(after.get("isPlaying", play))
        is_paused = bool(after.get("isPaused", False))

        return PlayModeManagementResult(
            success=True,
            is_playing=is_playing,
            is_paused=is_paused,
            previous_state=previous_state,
            warnings=warnings,
            message=f"Play mode state updated to {'playing' if is_playing else 'edit mode'}.",
        )
    except Exception as exc:
        logger.exception("Play mode management failed")
        return PlayModeManagementResult(
            success=False,
            error=str(exc),
            is_playing=not play,
            is_paused=False,
            previous_state=not play,
            warnings=[*warnings, f"Failed to change play mode: {exc}"],
            message="Play mode state update failed.",
        )


@mcp.tool()
async def save_scene(
    save_as_path: str | None = None,
    force_during_play_mode: bool = False,
) -> SaveSceneResult:
    """
    Safely saves the currently active Unity scene.
    Prevents scene saving during Play Mode to protect against scene corruption.

    Args:
        save_as_path: Optional path to save scene as a new asset. If None, saves active scene in-place.
        force_during_play_mode: If True, bypasses Play Mode save check (CAUTION: can corrupt scene).

    Returns:
        A SaveSceneResult detailing save status, path, and dirty state.
    """
    try:
        state = await get_editor_state(include_scene_details=False)
        if not state.success:
            return SaveSceneResult(
                success=False,
                error=f"Could not verify editor state before save: {state.error}",
                message="Save aborted: editor state verification failed.",
            )

        if state.is_playing and not force_during_play_mode:
            msg = (
                "Save scene rejected: Unity is in Play Mode. "
                "Saving during Play Mode will bake temporary runtime objects into the scene file and corrupt it. "
                "Exit Play Mode before saving, or set force_during_play_mode=True if absolutely intentional."
            )
            logger.warning(msg)
            return SaveSceneResult(
                success=False,
                error=msg,
                scene_name=state.active_scene_name,
                scene_path=state.active_scene_path,
                was_dirty=state.active_scene_dirty or False,
                is_saved=False,
                warnings=["Save blocked due to active Play Mode."],
                message="Scene save blocked to prevent corruption in Play Mode.",
            )

        if state.is_compiling:
            return SaveSceneResult(
                success=False,
                error="Cannot save scene while Unity is compiling scripts.",
                scene_name=state.active_scene_name,
                scene_path=state.active_scene_path,
                was_dirty=state.active_scene_dirty or False,
                is_saved=False,
                warnings=["Unity is currently compiling."],
                message="Scene save blocked: editor is compiling.",
            )

        # Attempt high-level C# save via EditorSceneManager
        save_res = await bridge.execute_code(_save_scene_code(save_as_path))
        if save_res.get("success") and isinstance(save_res.get("result"), dict):
            res_data = cast(dict[str, Any], save_res["result"])
            saved = bool(res_data.get("saved", False))
            was_dirty = bool(res_data.get("wasDirty", False))
            scene_name = cast(str | None, res_data.get("sceneName", state.active_scene_name))
            scene_path = cast(str | None, res_data.get("scenePath", state.active_scene_path))

            return SaveSceneResult(
                success=saved,
                error=None if saved else "EditorSceneManager.SaveScene returned false.",
                scene_name=scene_name,
                scene_path=scene_path,
                was_dirty=was_dirty,
                is_saved=saved,
                warnings=["Force saved during Play Mode."] if state.is_playing else [],
                message="Scene saved successfully." if saved else "Failed to save scene.",
            )

        # Fallback to bridge save endpoint
        fallback_res = await bridge.save_scene()
        saved = bool(fallback_res.get("success", False))
        return SaveSceneResult(
            success=saved,
            error=None if saved else str(fallback_res.get("error", "Bridge save_scene failed")),
            scene_name=state.active_scene_name,
            scene_path=state.active_scene_path,
            was_dirty=state.active_scene_dirty or False,
            is_saved=saved,
            warnings=["Saved via fallback bridge endpoint."],
            message="Scene saved via bridge fallback." if saved else "Fallback save failed.",
        )
    except Exception as exc:
        logger.exception("save_scene failed")
        return SaveSceneResult(
            success=False,
            error=str(exc),
            is_saved=False,
            message="Scene save failed with exception.",
        )


@mcp.tool()
async def safe_transaction(  # noqa: PLR0913
    editor_code: str,
    auto_save: bool = False,
    record_undo: bool = True,
    undo_name: str = "Visora Safe Transaction",
    restore_on_failure: bool = True,
    timeout_seconds: float = 60.0,
) -> SafeTransactionResult:
    """
    Executes C# editor code safely within an Undo group transaction, with automatic rollback on error.

    Args:
        editor_code: The C# editor script string to compile and execute.
        auto_save: If True, saves the scene before and after transaction (Edit Mode only).
        record_undo: If True, registers an Undo group before executing code.
        undo_name: Label for the registered Unity Undo group.
        restore_on_failure: If True, reverts changes via Undo rollback if code execution fails.
        timeout_seconds: Idle wait timeout.

    Returns:
        A SafeTransactionResult detailing transaction ID, undo group, rollback status, and result.
    """
    transaction_id = str(uuid.uuid4())
    warnings: list[str] = []
    undo_group: int | None = None
    scene_saved = False
    rolled_back = False

    try:
        # Step 1: Check editor state & idle
        state = await get_editor_state(include_scene_details=False)
        if not state.success:
            return SafeTransactionResult(
                success=False,
                error=f"Editor state check failed: {state.error}",
                transaction_id=transaction_id,
                scene_saved=False,
                warnings=["Could not verify editor state."],
                message="Transaction aborted: editor unavailable.",
            )

        if state.is_compiling:
            idle_res = await wait_for_editor_idle(timeout_seconds=timeout_seconds)
            if not idle_res.success:
                return SafeTransactionResult(
                    success=False,
                    error="Unity is compiling scripts and did not become idle in time.",
                    transaction_id=transaction_id,
                    scene_saved=False,
                    warnings=["Editor was busy compiling."],
                    message="Transaction aborted: editor compiling.",
                )

        # Step 2: Pre-transaction save and undo group registration
        scene_saved = await _handle_pre_transaction_save(auto_save, state.is_playing, warnings, save_scene)
        undo_group = await _register_undo_group(bridge, record_undo, undo_name, warnings)

        # Step 3: Execute editor code
        result: dict[str, Any] = await bridge.execute_code(editor_code)
        logs: list[str] = cast(list[str], result.get("logs", []))

        if not result.get("success", True) or result.get("error"):
            err_msg = str(result.get("error", "Code execution failed"))
            if restore_on_failure:
                rolled_back = await _execute_undo_rollback(bridge, undo_group, warnings)

            return SafeTransactionResult(
                success=False,
                error=err_msg,
                transaction_id=transaction_id,
                scene_saved=scene_saved,
                undo_group=undo_group,
                rolled_back=rolled_back,
                execution_result=result.get("result"),
                logs=logs,
                warnings=warnings,
                message="Transaction failed" + (" and rolled back." if rolled_back else "."),
            )

        # Step 4: Post-transaction save
        post_saved = await _handle_post_transaction_save(auto_save, state.is_playing, warnings, save_scene)
        scene_saved = scene_saved and post_saved if auto_save else False

        return SafeTransactionResult(
            success=True,
            transaction_id=transaction_id,
            scene_saved=scene_saved,
            undo_group=undo_group,
            rolled_back=False,
            execution_result=result.get("result"),
            logs=logs,
            warnings=warnings,
            message="Transaction executed successfully.",
        )
    except Exception as exc:
        logger.exception(f"Safe transaction {transaction_id} failed with exception")
        if restore_on_failure:
            rolled_back = await _execute_undo_rollback(bridge, undo_group, warnings)

        return SafeTransactionResult(
            success=False,
            error=str(exc),
            transaction_id=transaction_id,
            scene_saved=scene_saved,
            undo_group=undo_group,
            rolled_back=rolled_back,
            warnings=[*warnings, f"Exception occurred: {exc}"],
            message="Safe transaction failed with exception.",
        )


@mcp.tool()
async def restore_scene_state(
    undo_group: int | None = None,
    reload_active_scene: bool = False,
) -> RestoreSceneResult:
    """
    Restores scene state by reverting an Undo group or reloading the active scene from disk.

    Args:
        undo_group: Optional Unity Undo group index to revert down to.
        reload_active_scene: If True, reloads the active scene from disk, discarding unsaved changes.

    Returns:
        A RestoreSceneResult detailing revert and reload outcomes.
    """
    reverted_undo = False
    reloaded_scene = False
    warnings: list[str] = []
    active_scene_name: str | None = None

    try:
        if undo_group is not None:
            undo_res = await bridge.execute_code(_undo_transaction_code(undo_group))
            if undo_res.get("success") and isinstance(undo_res.get("result"), dict):
                reverted_undo = bool(undo_res["result"].get("reverted", False))
            else:
                warnings.append(f"Undo revert failed: {undo_res.get('error', 'Unknown error')}")

        if reload_active_scene:
            state = await get_editor_state(include_scene_details=False)
            if state.is_playing:
                return RestoreSceneResult(
                    success=False,
                    error="Cannot reload scene from disk while in Play Mode. Exit Play Mode first.",
                    reverted_undo=reverted_undo,
                    reloaded_scene=False,
                    warnings=["Scene reload blocked during Play Mode."],
                    message="Restore aborted: scene cannot be reloaded during Play Mode.",
                )

            reload_res = await bridge.execute_code(_reload_scene_code())
            if reload_res.get("success") and isinstance(reload_res.get("result"), dict):
                reloaded_data = cast(dict[str, Any], reload_res["result"])
                reloaded_scene = bool(reloaded_data.get("reloaded", False))
                active_scene_name = cast(str | None, reloaded_data.get("sceneName"))
            else:
                err = str(reload_res.get("error", "Reload scene failed"))
                return RestoreSceneResult(
                    success=False,
                    error=err,
                    reverted_undo=reverted_undo,
                    reloaded_scene=False,
                    warnings=[*warnings, err],
                    message="Failed to reload scene from disk.",
                )

        if not reverted_undo and not reloaded_scene:
            return RestoreSceneResult(
                success=False,
                error="No restore action taken: neither undo_group was specified nor reload_active_scene was True.",
                warnings=warnings,
                message="No restore action performed.",
            )

        return RestoreSceneResult(
            success=True,
            reverted_undo=reverted_undo,
            reloaded_scene=reloaded_scene,
            active_scene_name=active_scene_name,
            warnings=warnings,
            message="Scene state restored successfully.",
        )
    except Exception as exc:
        logger.exception("restore_scene_state failed")
        return RestoreSceneResult(
            success=False,
            error=str(exc),
            reverted_undo=reverted_undo,
            reloaded_scene=reloaded_scene,
            active_scene_name=active_scene_name,
            warnings=[*warnings, f"Restore exception: {exc}"],
            message="Scene state restore failed.",
        )


__all__ = [
    "_begin_undo_group_code",
    "_execute_undo_rollback",
    "_get_scene_details_code",
    "_handle_post_transaction_save",
    "_handle_pre_transaction_save",
    "_register_undo_group",
    "_reload_scene_code",
    "_save_scene_code",
    "_sleep",
    "_undo_transaction_code",
    "bridge",
    "get_editor_state",
    "playmode_management",
    "restore_scene_state",
    "safe_transaction",
    "save_scene",
    "wait_for_editor_idle",
]
