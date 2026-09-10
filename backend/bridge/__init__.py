"""
Visora Unity Bridge package.
Provides HTTP transport, port discovery, retry mechanics, and structured exceptions for Unity Editor integration.
"""

from backend.bridge.client import UnityBridge
from backend.bridge.exceptions import (
    BridgeBusyError,
    BridgeConnectionError,
    BridgeError,
    BridgeExecutionError,
    BridgeHTTPError,
    BridgeProtocolError,
    BridgeStateError,
    BridgeTimeoutError,
)

__all__ = [
    "BridgeBusyError",
    "BridgeConnectionError",
    "BridgeError",
    "BridgeExecutionError",
    "BridgeHTTPError",
    "BridgeProtocolError",
    "BridgeStateError",
    "BridgeTimeoutError",
    "UnityBridge",
]
