from pydantic import Field

from backend.schemas.base import BaseToolResult


class SkinnedMeshDiagnosticsResult(BaseToolResult):
    """Result schema for skinned mesh diagnostics."""

    has_bounds_issue: bool = Field(default=False, description="True if the mesh bounds are off-screen or zero-sized")
    bounds_center: list[float] | None = Field(default=None, description="Bounding box center coordinates [x, y, z]")
    bounds_size: list[float] | None = Field(default=None, description="Bounding box size dimensions [x, y, z]")
    material_count: int = Field(default=0, description="Number of materials attached to the renderer")
    bone_count: int = Field(default=0, description="Number of bones bound to the skinned mesh renderer")
    is_sub_mesh_valid: bool = Field(default=True, description="True if all sub-meshes are valid and non-empty")
    warnings: list[str] = Field(default_factory=list, description="List of non-blocking diagnostic warning messages")
