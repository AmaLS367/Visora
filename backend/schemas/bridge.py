from pydantic import BaseModel, Field

from backend.schemas.base import BaseToolResult


class PortScanResult(BaseModel):
    """Result of scanning an individual candidate port for Unity bridge availability."""

    port: int = Field(..., description="The port number tested")
    is_open: bool = Field(..., description="Whether the port is actively responding to AnkleBreaker ping")
    latency_ms: float | None = Field(default=None, description="Roundtrip ping latency in milliseconds, if open")


class EditorStateInfo(BaseModel):
    """Snapshot of Unity Editor operational state."""

    is_playing: bool = Field(default=False, description="Whether Unity Editor is currently in Play Mode")
    is_paused: bool = Field(default=False, description="Whether Unity Editor playback is currently paused")
    is_compiling: bool = Field(default=False, description="Whether Unity Editor is currently compiling scripts")
    active_scene: str | None = Field(default=None, description="Path or name of the currently active scene")
    unity_version: str | None = Field(default=None, description="Unity Editor version if reported by bridge")


class BridgeStatusResult(BaseToolResult):
    """Detailed health and availability status of the Unity bridge connection."""

    connected: bool = Field(..., description="Whether a functional connection to Unity Editor bridge is established")
    active_port: int | None = Field(default=None, description="The currently active/selected bridge port")
    bridge_url: str = Field(..., description="Base URL used for the bridge connection")
    latency_ms: float | None = Field(
        default=None, description="Round-trip latency to the active bridge in milliseconds"
    )
    scanned_ports: list[PortScanResult] = Field(
        default_factory=list, description="Results of scanning candidate bridge ports"
    )
    editor_state: EditorStateInfo | None = Field(
        default=None, description="Current Unity Editor state snapshot (play mode, compiling, active scene)"
    )
    message: str = Field(..., description="Human and agent-readable summary of bridge health and status")
    troubleshooting: str | None = Field(
        default=None, description="Actionable troubleshooting steps if bridge is disconnected or degraded"
    )
