from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.base import BaseToolResult


class DiagnosticIssue(BaseModel):
    """Structured description of an issue found during mesh diagnostics."""

    category: str = Field(
        description="Category of issue: 'geometry_skinning', 'texture_material', 'bounds', 'deformation', or 'hierarchy'"
    )
    severity: str = Field(default="warning", description="Severity level: 'error', 'warning', or 'info'")
    message: str = Field(description="Human-readable description of the detected issue")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional structured diagnostic metadata and context"
    )


class BoundsInfo(BaseModel):
    """Diagnostics for local and world bounding boxes of the skinned mesh."""

    local_center: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        description="Local bounding box center coordinates [x, y, z]",
    )
    local_size: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        description="Local bounding box size dimensions [x, y, z]",
    )
    world_center: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        description="World bounding box center coordinates [x, y, z]",
    )
    world_size: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0],
        description="World bounding box size dimensions [x, y, z]",
    )
    is_zero_volume: bool = Field(
        default=False,
        description="True if any dimension of the bounding box is zero or negative",
    )
    is_abnormal: bool = Field(
        default=False,
        description="True if bounds contain NaN/Inf coordinates or are unrealistically huge (>1000m)",
    )
    update_when_offscreen: bool = Field(
        default=False,
        description="True if SkinnedMeshRenderer.updateWhenOffscreen is enabled",
    )


class BoneBindingInfo(BaseModel):
    """Diagnostics for an individual bone attachment in the SkinnedMeshRenderer bones array."""

    bone_index: int = Field(description="0-based index in the renderer.bones array")
    bone_name: str | None = Field(default=None, description="Name of the bone transform")
    bone_path: str | None = Field(default=None, description="Hierarchy path to the bone transform")
    is_null: bool = Field(default=False, description="True if this bone slot is unassigned / null")
    has_bindpose: bool = Field(
        default=True,
        description="True if a corresponding bindpose matrix exists in mesh.bindposes",
    )


class MaterialSlotInfo(BaseModel):
    """Diagnostics for an individual material slot on the renderer."""

    slot_index: int = Field(description="0-based index in the renderer.sharedMaterials array")
    material_name: str | None = Field(default=None, description="Material asset name")
    shader_name: str | None = Field(default=None, description="Shader name used by the material")
    is_missing: bool = Field(default=False, description="True if the material slot is unassigned / null")
    is_error_shader: bool = Field(
        default=False,
        description="True if using an error/fallback shader (e.g., Hidden/InternalErrorShader pink shader)",
    )
    main_texture_name: str | None = Field(
        default=None,
        description="Primary texture asset name if assigned",
    )
    has_main_texture: bool = Field(
        default=False,
        description="True if a primary texture is assigned to the material",
    )


class SubMeshInfo(BaseModel):
    """Diagnostics for an individual submesh within the sharedMesh."""

    submesh_index: int = Field(description="0-based index of the submesh")
    vertex_count: int = Field(default=0, description="Vertex count referenced by this submesh")
    triangle_count: int = Field(default=0, description="Triangle/index count of this submesh")
    has_matching_material: bool = Field(
        default=True,
        description="True if there is a corresponding valid material slot assigned for this submesh",
    )
    topology: str = Field(default="Triangles", description="Submesh topology type (e.g., Triangles, Quads)")


class DeformationInfo(BaseModel):
    """Diagnostics for blendshapes, bone scaling, and deformation integrity."""

    has_blendshapes: bool = Field(default=False, description="True if mesh has blendshapes")
    blendshape_count: int = Field(default=0, description="Total number of blendshapes in mesh")
    active_blendshapes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Active blendshapes with non-zero weights [{'name': str, 'weight': float}]",
    )
    root_bone_path: str | None = Field(default=None, description="Hierarchy path to the rootBone transform")
    root_bone_scale: list[float] | None = Field(
        default=None,
        description="Lossy scale of root bone [x, y, z]",
    )
    has_non_uniform_or_zero_scale: bool = Field(
        default=False,
        description="True if root bone or bone hierarchy has 0, negative, or degenerate scale",
    )


class SkinnedMeshDiagnosticsResult(BaseToolResult):
    """Result schema for skinned mesh diagnostics."""

    mesh_renderer_path: str | None = Field(
        default=None,
        description="Hierarchical path to the inspected SkinnedMeshRenderer GameObject",
    )
    mesh_name: str | None = Field(default=None, description="Name of the sharedMesh asset")
    vertex_count: int = Field(default=0, description="Total vertex count of the mesh")
    submesh_count: int = Field(default=0, description="Number of submeshes in the mesh")
    material_count: int = Field(default=0, description="Number of materials attached to the renderer")
    bone_count: int = Field(default=0, description="Number of bones bound to the skinned mesh renderer")
    bounds_center: list[float] | None = Field(default=None, description="Bounding box center coordinates [x, y, z]")
    bounds_size: list[float] | None = Field(default=None, description="Bounding box size dimensions [x, y, z]")
    is_sub_mesh_valid: bool = Field(default=True, description="True if all sub-meshes are valid and have materials")
    has_bounds_issue: bool = Field(default=False, description="True if the mesh bounds are off-screen or zero-sized")
    has_broken_bones: bool = Field(
        default=False,
        description="True if null bones, missing root bone, or missing bindposes detected",
    )
    has_material_mismatch: bool = Field(
        default=False,
        description="True if submesh count != material count or missing materials/shaders",
    )
    has_deformation_issue: bool = Field(
        default=False,
        description="True if abnormal scaling, extreme blendshapes, or NaN/Inf vertices found",
    )
    primary_issue_category: str = Field(
        default="none",
        description="Primary issue category: 'geometry_skinning', 'texture_material', 'bounds', 'deformation', or 'none'",
    )
    bounds: BoundsInfo | None = Field(default=None, description="Detailed bounding box diagnostics")
    bone_bindings: list[BoneBindingInfo] = Field(
        default_factory=list,
        description="Diagnostics for each bone binding slot",
    )
    materials: list[MaterialSlotInfo] = Field(
        default_factory=list,
        description="Diagnostics for each material slot",
    )
    submeshes: list[SubMeshInfo] = Field(
        default_factory=list,
        description="Diagnostics for each submesh",
    )
    deformation: DeformationInfo | None = Field(
        default=None,
        description="Deformation, scaling, and blendshape diagnostics",
    )
    issues: list[DiagnosticIssue] = Field(
        default_factory=list,
        description="Structured list of all detected issues",
    )
    warnings: list[str] = Field(default_factory=list, description="List of non-blocking diagnostic warning messages")
