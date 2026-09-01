import logging

from backend.bridge import UnityBridge

logger = logging.getLogger("backend.tools.mesh")
bridge = UnityBridge()

__all__ = ["bridge", "logger"]
