from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.base import BaseToolResult


class BodyPenetrationEvent(BaseModel):
    """Details of a single body mesh or capsule penetration event."""

    model_config = ConfigDict(extra="ignore")

    time: float = Field(..., description="Timestamp in clip (seconds)")
    limb_a: str = Field(..., description="First colliding limb/segment")
    limb_b: str = Field(..., description="Second colliding limb/segment")
    penetration_depth_meters: float = Field(..., description="Depth of interpenetration (meters)")
    severity: Literal["critical", "warning", "unknown"] = Field(
        ..., description="Severity level: critical (> 5cm), warning, or unknown"
    )
    description: str = Field(..., description="Human-readable description of penetration")


class SelfIntersectionResult(BaseToolResult):
    """Result of analyzing character mesh self-intersections and body clipping."""

    model_config = ConfigDict(extra="ignore")

    target_object_path: str = Field(default="", description="Target character GameObject path")
    clip_path: str = Field(default="", description="Project-relative path to AnimationClip")
    intersections_found: int = Field(default=0, description="Total number of penetration events detected")
    sample_count: int = Field(default=0, description="Total sampled frames across animation")
    clean_interval_percent: float = Field(default=100.0, description="Percentage of sampled frames free of penetration")
    max_penetration_depth: float = Field(default=0.0, description="Maximum penetration depth (meters)")
    penetrations: list[BodyPenetrationEvent] = Field(
        default_factory=list, description="List of detected penetration events"
    )
    warnings: list[str] = Field(default_factory=list, description="Rig, proxy, or sampling advisories")
