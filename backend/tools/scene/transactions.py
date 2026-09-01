import logging
from collections.abc import Awaitable, Callable
from typing import cast

import httpx

from backend.bridge import UnityBridge
from backend.schemas import SaveSceneResult
from backend.tools.scene.scripts import _begin_undo_group_code, _undo_transaction_code

logger = logging.getLogger("backend.tools.scene.transactions")

_BRIDGE_ERRORS = (httpx.HTTPError, ConnectionError, OSError, ValueError, KeyError, TypeError, RuntimeError)


async def _execute_undo_rollback(bridge: UnityBridge, undo_group: int | None, warnings: list[str]) -> bool:
    """Helper to revert changes to a recorded Undo group."""
    if undo_group is None:
        return False
    try:
        await bridge.execute_code(_undo_transaction_code(undo_group))
        return True
    except _BRIDGE_ERRORS as rb_err:
        warnings.append(f"Undo rollback failed: {rb_err}")
        return False


async def _register_undo_group(
    bridge: UnityBridge, record_undo: bool, undo_name: str, warnings: list[str]
) -> int | None:
    """Helper to register and name an Undo group."""
    if not record_undo:
        return None
    try:
        undo_res = await bridge.execute_code(_begin_undo_group_code(undo_name))
        if undo_res.get("success") and isinstance(undo_res.get("result"), dict):
            return cast(int, undo_res["result"].get("undoGroup"))
    except _BRIDGE_ERRORS as e:
        logger.warning(f"Could not record undo group: {e}")
        warnings.append(f"Undo group registration failed: {e}")
    return None


async def _handle_pre_transaction_save(
    auto_save: bool,
    is_playing: bool,
    warnings: list[str],
    save_scene_fn: Callable[[], Awaitable[SaveSceneResult]],
) -> bool:
    """Helper for pre-transaction auto-save in Edit Mode."""
    if not auto_save:
        return False
    if is_playing:
        warnings.append("Pre-transaction auto-save skipped because editor is in Play Mode.")
        return False
    save_res = await save_scene_fn()
    if not save_res.success:
        warnings.append(f"Pre-transaction scene save warning: {save_res.error}")
    return save_res.is_saved


async def _handle_post_transaction_save(
    auto_save: bool,
    is_playing: bool,
    warnings: list[str],
    save_scene_fn: Callable[[], Awaitable[SaveSceneResult]],
) -> bool:
    """Helper for post-transaction auto-save in Edit Mode."""
    if not auto_save or is_playing:
        return True
    post_save = await save_scene_fn()
    if not post_save.success:
        warnings.append(f"Post-transaction scene save warning: {post_save.error}")
    return post_save.is_saved
