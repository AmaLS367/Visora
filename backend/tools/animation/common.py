import logging

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.animation")
bridge = UnityBridge()

__all__ = ["bridge", "logger"]
