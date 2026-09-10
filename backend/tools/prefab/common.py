import logging
from typing import Any

from backend.bridge import UnityBridge
from backend.tools.errors import bridge_error

logger = logging.getLogger("backend.tools.prefab")
bridge = UnityBridge()

_READY_TIMEOUT_SECONDS = 15.0


async def bridge_supports(feature: str) -> bool:
    """
    Treat a missing or unreachable capability as unavailable instead of hiding the reason.

    Goes through `prefab_pkg.bridge` (a deferred import of the package itself) rather than this
    module's own `bridge` name so that tests which rebind `backend.tools.prefab.bridge` are
    honoured - the same indirection `backend.tools.animation.common` relies on.
    """
    import backend.tools.prefab as prefab_pkg  # noqa: PLC0415

    try:
        return bool(await prefab_pkg.bridge.supports_feature(feature))
    except Exception as exc:
        logger.info("Bridge capability '%s' could not be confirmed: %s", feature, exc)
        return False


async def native_preflight(capability: str, operation: str) -> dict[str, Any] | None:
    """
    Failure fields for a native-only prefab tool, or None when Unity can take the request.

    The order is deliberate: the capability comes first so a legacy bridge is never probed further
    (and never sent improvised C#), then Unity must be idle, then in Edit Mode. A busy Editor keeps
    its retry hints via `bridge_error`.
    """
    import backend.tools.prefab as prefab_pkg  # noqa: PLC0415

    if not await bridge_supports(capability):
        return {
            "success": False,
            "error": (
                f"Unity bridge does not support capability '{capability}'. {operation} requires the "
                "Visora Unity package; update it or switch UNITY_BRIDGE_MODE to native."
            ),
        }

    try:
        editor_state = await prefab_pkg.bridge.wait_for_editor_ready(timeout_seconds=_READY_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("Unity did not become idle before %s: %s", operation, exc)
        return bridge_error(exc)

    if bool(editor_state.get("isPlaying", False)):
        return {"success": False, "error": f"{operation} requires Edit Mode; exit Play Mode and retry."}
    return None


def optional_asset_path(value: Any) -> str | None:
    """A bridge-reported project path with forward slashes, or None when it is absent or blank."""
    if not value:
        return None
    clean = str(value).replace("\\", "/").strip().lstrip("/")
    return clean or None


def normalize_hierarchy_path(path: Any, *, field: str = "instance_path") -> tuple[str, str | None]:
    """
    Normalize a root-anchored scene hierarchy path ('Root/Child/Leaf', segments optionally indexed
    as 'Name[k]' - the same convention Prefab relative paths use).

    Only the outer whitespace and leading/trailing slashes are trimmed: GameObject names may contain
    spaces or backslashes, so segments are passed through untouched. Returns `(clean, error)`.
    """
    raw = "" if path is None else str(path)
    clean = raw.strip().strip("/")
    if not clean:
        return clean, f"{field} is required."
    if any(not segment for segment in clean.split("/")):
        return clean, f"{field} '{clean}' contains an empty segment."
    return clean, None


__all__ = [
    "bridge",
    "bridge_supports",
    "logger",
    "native_preflight",
    "normalize_hierarchy_path",
    "optional_asset_path",
]
