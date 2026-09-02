import logging

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.asset")
bridge = UnityBridge()

__all__ = ["bridge", "logger"]
