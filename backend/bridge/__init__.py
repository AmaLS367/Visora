"""
Visora Unity Bridge package.
Provides HTTP transport, port discovery, retry mechanics, and structured exceptions for Unity Editor integration.
"""

from backend.bridge.client import UnityBridge
from backend.bridge.exceptions import (
    BridgeConnectionError,
    BridgeError,
    BridgeExecutionError,
    BridgeHTTPError,
    BridgeStateError,
    BridgeTimeoutError,
)

__all__ = [
    "BridgeConnectionError",
    "BridgeError",
    "BridgeExecutionError",
    "BridgeHTTPError",
    "BridgeStateError",
    "BridgeTimeoutError",
    "UnityBridge",
]
