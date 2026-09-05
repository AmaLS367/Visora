import logging
from typing import Any

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.animation")
bridge = UnityBridge()


async def _bridge_supports(feature: str) -> bool:
    """
    Treat a missing or unreachable capability as unavailable instead of hiding the reason.

    Goes through `animation_pkg.bridge` (a deferred import of the package itself) rather than
    this module's own `bridge` name, on purpose: existing tests monkeypatch
    `backend.tools.animation.bridge` (e.g. `test_animation_preview.py`,
    `test_animation_authoring.py`), which only rebinds that package's attribute, not this
    module's. Calling through the package picks up whatever the current test — or production
    startup — has bound there.
    """
    import backend.tools.animation as animation_pkg  # noqa: PLC0415

    try:
        return bool(await animation_pkg.bridge.supports_feature(feature))
    except Exception as exc:
        logger.info("Bridge capability '%s' could not be confirmed: %s", feature, exc)
        return False


async def _require_edit_mode() -> str | None:
    """
    Returns an error message when Unity is in Play Mode, else None. Mutating a clip mid-Play
    Mode is meaningless (the change would not persist), matching the constraint
    `preview_animation` already enforces for sampling. Every clip-authoring tool calls this
    before writing a backup or touching the clip. Same package-indirection reason as
    `_bridge_supports` above for going through `animation_pkg.bridge`.
    """
    import backend.tools.animation as animation_pkg  # noqa: PLC0415

    try:
        editor_state = await animation_pkg.bridge.get_editor_state()
    except Exception as exc:
        return f"Could not confirm Unity editor state: {exc}"
    if bool(editor_state.get("isPlaying", False)):
        return "Clip authoring requires Edit Mode; exit Play Mode before editing this clip."
    return None


def _unwrap_legacy_result(response: dict[str, Any]) -> dict[str, Any]:
    """
    `execute_code` (the legacy AnkleBreaker path) returns
    `{"success": <did it compile and run>, "result": <the snippet's own return value>, "logs": [...]}`
    — confirmed against `NativeCodeExecutionService.ExecuteAsync`. The outer `success` is about
    execution, not about whether the *operation* (e.g. "clip not found") succeeded; reading it
    directly reports a business-logic failure as a hollow success. `inspect_animation_clip`
    already unwraps this correctly (`backend/tools/animation/inspector.py`) — this mirrors it,
    shared here so `authoring.py` and `backups.py` (Tasks 8-9) do not each redefine it. The
    native path never has this wrapper, so it is only ever called on an `execute_code` result.
    """
    result = response.get("result")
    return result if isinstance(result, dict) else response


__all__ = [
    "_bridge_supports",
    "_require_edit_mode",
    "_unwrap_legacy_result",
    "bridge",
    "logger",
]

