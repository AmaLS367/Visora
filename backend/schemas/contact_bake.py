from __future__ import annotations

from pydantic import ConfigDict, Field

from backend.schemas.base import BaseToolResult


class BakeEffectorContactResult(BaseToolResult):
    """Result of baking generalized 3D effector contact curves into an AnimationClip."""

    model_config = ConfigDict(extra="ignore")

    clip_path: str = Field(default="", description="Project-relative path to the AnimationClip")
    effector: str = Field(default="", description="Effector name (e.g. left_foot, right_hand)")
    backup_id: str | None = Field(default=None, description="Pre-mutation backup identifier in VisoraBackups/")
    keyframes_modified_count: int = Field(default=0, description="Total keyframe channels written to clip")
    max_effector_displacement: float = Field(
        default=0.0, description="Maximum displacement (meters) applied to effector"
    )
    residual_error: float = Field(default=0.0, description="Maximum residual distance error (meters) to target")
    active_duration: float = Field(default=0.0, description="Total duration (seconds) with contact or blend influence")
    warnings: list[str] = Field(default_factory=list, description="Advisories or boundary warnings")
