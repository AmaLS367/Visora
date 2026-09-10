from __future__ import annotations

from pydantic import ConfigDict, Field

from backend.schemas.base import BaseToolResult


class CameraSubjectContactResult(BaseToolResult):
    """Result of solving coordinated camera recoil, hit-stop, and lens impact."""

    model_config = ConfigDict(extra="ignore")

    character_backup_id: str | None = Field(default=None, description="Backup ID for character clip")
    camera_backup_id: str | None = Field(default=None, description="Backup ID for camera clip")
    impact_world_position: list[float] = Field(
        default_factory=list,
        description="World coordinates [x, y, z] of solved impact point",
    )
    impact_screen_residual_pixels: list[float] = Field(
        default_factory=list,
        description="Screen pixel error [dx, dy] between effector and target lens viewport",
    )
    max_limb_reach_ratio: float = Field(default=0.0, description="Limb reach ratio (dist / max_reach)")
    keyframes_modified_count: int = Field(default=0, description="Total keyframe channels written")
    warnings: list[str] = Field(default_factory=list, description="Advisories, reach limits, or camera warnings")
