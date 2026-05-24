import logging
import uuid
from typing import Any

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import PlayModeManagementResult, SafeTransactionResult

logger = logging.getLogger("backend.tools.scene")
bridge = UnityBridge()


@mcp.tool()
async def safe_transaction(editor_code: str, auto_save: bool = True) -> SafeTransactionResult:
    """
    Executes editor scripting code in a safe transaction, saving the active scene first.

    Args:
        editor_code: The C# editor script string to compile and execute.
        auto_save: If True, saves the scene automatically before executing the transaction to prevent loss of state.

    Returns:
        A SafeTransactionResult detailing whether the scene was saved, transaction ID, and outcome description.
    """
    transaction_id = str(uuid.uuid4())

    try:
        state = await bridge.get_editor_state()
        if state.get("isPlaying") is True:
            await bridge.set_play_mode(False)

        scene_saved = False
        if auto_save:
            save_result = await bridge.save_scene()
            scene_saved = bool(save_result.get("success", False))

        result: dict[str, Any] = await bridge.execute_code(editor_code)
        if result.get("error"):
            return SafeTransactionResult(
                success=False,
                error=str(result["error"]),
                transaction_id=transaction_id,
                scene_saved=scene_saved,
                message="Unity editor code execution failed",
            )

        if auto_save:
            save_result = await bridge.save_scene()
            scene_saved = scene_saved and bool(save_result.get("success", False))

        return SafeTransactionResult(
            success=True,
            transaction_id=transaction_id,
            scene_saved=scene_saved,
            message="Transaction executed successfully",
        )
    except Exception as exc:
        logger.exception("Safe transaction failed")
        return SafeTransactionResult(
            success=False,
            error=str(exc),
            transaction_id=transaction_id,
            scene_saved=False,
            message="Safe transaction failed",
        )


@mcp.tool()
async def playmode_management(play: bool) -> PlayModeManagementResult:
    """
    Manages the Unity Editor Play Mode state.

    Args:
        play: Set to True to start play mode, or False to stop and exit back to edit mode.

    Returns:
        A PlayModeManagementResult detailing the playmode state change outcome.
    """
    try:
        before = await bridge.get_editor_state()
        previous_state = bool(before.get("isPlaying", False))
        await bridge.set_play_mode(play)
        after = await bridge.get_editor_state()
        is_playing = bool(after.get("isPlaying", play))

        return PlayModeManagementResult(
            success=True,
            is_playing=is_playing,
            previous_state=previous_state,
            message="Play mode state updated",
        )
    except Exception as exc:
        logger.exception("Play mode management failed")
        return PlayModeManagementResult(
            success=False,
            error=str(exc),
            is_playing=not play,
            previous_state=not play,
            message="Play mode state update failed",
        )
