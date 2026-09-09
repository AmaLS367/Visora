import logging
from collections.abc import Iterable
from typing import Any

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.animation")
bridge = UnityBridge()


def warns(resp: dict[str, Any]) -> list[str]:
    """Coerce a bridge response's `warnings` array to `list[str]`, tolerating a missing/None value."""
    raw = resp.get("warnings")
    if not isinstance(raw, Iterable) or isinstance(raw, str | bytes):
        return []
    return [str(w) for w in raw]


def coerce_literal(
    value: Any,
    allowed: set[str],
    warnings: list[str],
    *,
    field: str = "value",
    fallback: str = "unknown",
) -> Any:
    """
    Map a raw bridge string onto a known vocabulary.

    A value outside `allowed` is not an error - the native analysis that produced it may have
    fully succeeded - so record a warning and return `fallback` (which callers include in their
    Literal type) instead of letting Pydantic raise ValidationError and mislabel the whole call
    as a bridge failure. Returns Any so the result drops straight into a Literal-typed field;
    Pydantic still validates it against that field's real vocabulary.
    """
    text = str(value) if value is not None else ""
    if text in allowed:
        return text
    warnings.append(f"Unexpected {field} '{text}' from Unity bridge; treated as '{fallback}'.")
    return fallback


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
    "coerce_literal",
    "logger",
    "warns",
]
