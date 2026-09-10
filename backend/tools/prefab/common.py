import logging

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.prefab")
bridge = UnityBridge()


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


__all__ = ["bridge", "bridge_supports", "logger"]
