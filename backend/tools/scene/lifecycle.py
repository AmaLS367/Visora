from typing import Any, cast

import backend.tools.scene as scene_pkg
from backend.app import mcp
from backend.schemas import (
    PlayModeManagementResult,
    SaveSceneResult,
)
from backend.tools.scene.scripts import _save_scene_code
from backend.tools.scene.state import get_editor_state, wait_for_editor_idle


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

        before = await scene_pkg.bridge.get_editor_state()
        previous_state = bool(before.get("isPlaying", False))

        await scene_pkg.bridge.set_play_mode(play)

        if wait_for_idle:
            idle_after = await wait_for_editor_idle(timeout_seconds=timeout_seconds)
            if not idle_after.success:
                warnings.append(f"Editor was not idle after play mode change: {idle_after.error}")

        after = await scene_pkg.bridge.get_editor_state()
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
        scene_pkg.logger.exception("Play mode management failed")
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
            scene_pkg.logger.warning(msg)
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
        save_res = await scene_pkg.bridge.execute_code(_save_scene_code(save_as_path))
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
        fallback_res = await scene_pkg.bridge.save_scene()
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
        scene_pkg.logger.exception("save_scene failed")
        return SaveSceneResult(
            success=False,
            error=str(exc),
            is_saved=False,
            message="Scene save failed with exception.",
        )


__all__ = ["playmode_management", "save_scene"]
