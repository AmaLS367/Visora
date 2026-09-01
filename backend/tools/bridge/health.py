import logging

from backend.app import mcp
from backend.bridge import BridgeError, UnityBridge
from backend.schemas.bridge import (
    BridgeStatusResult,
    EditorStateInfo,
    PortScanResult,
)

logger = logging.getLogger("backend.tools.bridge.health")
bridge = UnityBridge()


@mcp.tool()
async def get_bridge_status(scan_all_ports: bool = True) -> BridgeStatusResult:
    """
    Checks the connectivity, health, active port, ping latency, and operational state of the Unity Editor AnkleBreaker bridge.

    Args:
        scan_all_ports: If True, scans all configured candidate ports and reports their status. Defaults to True.

    Returns:
        BridgeStatusResult with connection status, active port, latency, Unity Editor state, and troubleshooting hints.
    """
    scanned_ports: list[PortScanResult] = []

    if scan_all_ports:
        raw_scanned = await bridge.scan_available_ports()
        scanned_ports = [
            PortScanResult(
                port=s["port"],
                is_open=s["is_open"],
                latency_ms=s.get("latency_ms"),
            )
            for s in raw_scanned
        ]

    # Check connection and latency on active port
    is_connected, latency_ms = await bridge.ping()

    if not is_connected:
        return BridgeStatusResult(
            success=False,
            connected=False,
            active_port=None,
            bridge_url=bridge.base_url,
            latency_ms=None,
            scanned_ports=scanned_ports,
            editor_state=None,
            error="Unity bridge is unreachable",
            message=f"Unable to connect to Unity Editor on {bridge.base_url} across candidate ports.",
            troubleshooting=(
                "1. Ensure Unity Editor is open with your project.\n"
                "2. Verify the AnkleBreaker bridge package is installed and active in Unity.\n"
                "3. Check the Unity Console for compilation errors preventing the bridge from running.\n"
                "4. Check if a firewall is blocking local HTTP requests to port 7890/7891."
            ),
        )

    active_port = await bridge.get_active_port()

    # Query editor state
    editor_state: EditorStateInfo | None = None
    try:
        raw_state = await bridge.get_editor_state()
        editor_state = EditorStateInfo(
            is_playing=bool(raw_state.get("isPlaying", raw_state.get("is_playing", False))),
            is_paused=bool(raw_state.get("isPaused", raw_state.get("is_paused", False))),
            is_compiling=bool(raw_state.get("isCompiling", raw_state.get("is_compiling", False))),
            active_scene=raw_state.get("activeScene") or raw_state.get("active_scene"),
            unity_version=raw_state.get("unityVersion") or raw_state.get("unity_version"),
        )
    except BridgeError as e:
        logger.warning(f"Could not retrieve editor state during bridge health check: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error retrieving editor state: {e}")

    state_desc = []
    if editor_state:
        if editor_state.is_playing:
            state_desc.append("Play Mode")
        if editor_state.is_compiling:
            state_desc.append("Compiling")
        if editor_state.active_scene:
            state_desc.append(f"Scene: {editor_state.active_scene}")

    state_suffix = f" [{', '.join(state_desc)}]" if state_desc else ""

    return BridgeStatusResult(
        success=True,
        connected=True,
        active_port=active_port,
        bridge_url=bridge.base_url,
        latency_ms=latency_ms,
        scanned_ports=scanned_ports,
        editor_state=editor_state,
        error=None,
        message=f"Connected to Unity Editor on port {active_port} ({latency_ms}ms){state_suffix}.",
        troubleshooting=None,
    )
