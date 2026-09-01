import time
from typing import Any, cast

import backend.tools.scene as scene_pkg
from backend.app import mcp
from backend.schemas import (
    EditorStateResult,
    WaitForEditorIdleResult,
)
from backend.tools.scene.scripts import _get_scene_details_code


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
        raw_state = await scene_pkg.bridge.get_editor_state()
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
                scene_res = await scene_pkg.bridge.execute_capability(_get_scene_details_code())
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
                scene_pkg.logger.debug(f"Could not fetch extended scene details via C#: {e}")
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
        scene_pkg.logger.exception("get_editor_state failed")
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
            await scene_pkg._sleep(poll_interval_seconds)

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
        scene_pkg.logger.exception("wait_for_editor_idle failed")
        return WaitForEditorIdleResult(
            success=False,
            is_idle=False,
            waited_seconds=round(time.time() - start_time, 3),
            error=str(exc),
            warnings=[f"Error during idle wait: {exc}"],
            message="Error while waiting for editor idle state.",
        )


__all__ = ["get_editor_state", "wait_for_editor_idle"]
