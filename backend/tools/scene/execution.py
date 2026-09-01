import uuid
from typing import Any, cast

import backend.tools.scene as scene_pkg
from backend.app import mcp
from backend.schemas import (
    RestoreSceneResult,
    SafeTransactionResult,
)
from backend.tools.scene.lifecycle import save_scene
from backend.tools.scene.scripts import (
    _reload_scene_code,
    _undo_transaction_code,
)
from backend.tools.scene.state import get_editor_state, wait_for_editor_idle
from backend.tools.scene.transactions import (
    _execute_undo_rollback,
    _handle_post_transaction_save,
    _handle_pre_transaction_save,
    _register_undo_group,
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
        undo_group = await _register_undo_group(scene_pkg.bridge, record_undo, undo_name, warnings)

        # Step 3: Execute editor code
        result: dict[str, Any] = await scene_pkg.bridge.execute_capability(editor_code)
        logs: list[str] = cast(list[str], result.get("logs", []))

        if not result.get("success", True) or result.get("error"):
            err_msg = str(result.get("error", "Code execution failed"))
            if restore_on_failure:
                rolled_back = await _execute_undo_rollback(scene_pkg.bridge, undo_group, warnings)

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
        scene_pkg.logger.exception(f"Safe transaction {transaction_id} failed with exception")
        if restore_on_failure:
            rolled_back = await _execute_undo_rollback(scene_pkg.bridge, undo_group, warnings)

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
            undo_res = await scene_pkg.bridge.execute_capability(_undo_transaction_code(undo_group))
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

            reload_res = await scene_pkg.bridge.execute_capability(_reload_scene_code())
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
        scene_pkg.logger.exception("restore_scene_state failed")
        return RestoreSceneResult(
            success=False,
            error=str(exc),
            reverted_undo=reverted_undo,
            reloaded_scene=reloaded_scene,
            active_scene_name=active_scene_name,
            warnings=[*warnings, f"Restore exception: {exc}"],
            message="Scene state restore failed.",
        )


__all__ = ["restore_scene_state", "safe_transaction"]
