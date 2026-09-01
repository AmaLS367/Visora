import asyncio
import logging

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.scene")
bridge = UnityBridge()


async def _sleep(seconds: float) -> None:
    """Sleep helper to facilitate deterministic testing."""
    await asyncio.sleep(seconds)


__all__ = ["_sleep", "bridge", "logger"]
