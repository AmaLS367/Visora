import asyncio
import logging

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.vision")
bridge = UnityBridge()


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


__all__ = ["_sleep", "bridge", "logger"]
