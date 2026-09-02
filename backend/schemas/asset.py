from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.base import BaseToolResult


class AssetSearchResultItem(BaseModel):
    """Represents a single 3D asset or texture discovered via web search."""

    id: str = Field(..., description="Unique identifier for the asset")
    name: str = Field(..., description="Display title or name of the asset")
    source: str = Field(..., description="Source provider (e.g., ambientcg, sketchfab, polypizza, direct)")
    category: str = Field(default="model", description="Category: model, texture, material, environment, prop")
    description: str | None = Field(default=None, description="Short description or summary")
    thumbnail_url: str | None = Field(default=None, description="Preview thumbnail image URL")
    author: str | None = Field(default=None, description="Creator or author name")
    license: str | None = Field(default=None, description="Asset license (e.g., CC0, CC-BY 4.0)")
    file_formats: list[str] = Field(default_factory=list, description="Available formats: glb, fbx, obj, zip")
    download_url: str | None = Field(default=None, description="Direct download URL if available")
    details: dict[str, Any] = Field(default_factory=dict, description="Provider-specific metadata (poly count, etc.)")


class SearchAssetsResult(BaseToolResult):
    """Result schema for 3D asset web discovery."""

    query: str = Field(..., description="Original search query string")
    source: str = Field(default="all", description="Source provider queried")
    total_count: int = Field(default=0, description="Total count of discovered assets")
    items: list[AssetSearchResultItem] = Field(default_factory=list, description="List of discovered asset items")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking provider warnings")


class DownloadAndImportAssetResult(BaseToolResult):
    """Result schema for downloading and importing an asset into Unity."""

    asset_path: str | None = Field(default=None, description="Relative Unity asset path (e.g. Assets/.../model.glb)")
    absolute_path: str | None = Field(default=None, description="Absolute filesystem path on disk")
    file_size_bytes: int = Field(default=0, description="Size of downloaded file in bytes")
    is_archive: bool = Field(default=False, description="True if downloaded file was extracted from an archive")
    extracted_files: list[str] = Field(default_factory=list, description="Relative paths of extracted files if archive")
    imported_objects: list[str] = Field(
        default_factory=list, description="Unity asset paths registered in AssetDatabase"
    )
    instantiated_game_object: str | None = Field(
        default=None, description="Scene path of instantiated GameObject if requested"
    )
    instance_id: int | None = Field(default=None, description="Unity Instance ID of instantiated GameObject")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings during download or import")


class ImportLocalAssetResult(BaseToolResult):
    """Result schema for importing a local file into the Unity project."""

    asset_path: str | None = Field(default=None, description="Target asset path inside Unity project")
    absolute_path: str | None = Field(default=None, description="Absolute filesystem path inside project Assets")
    file_size_bytes: int = Field(default=0, description="File size in bytes")
    imported_objects: list[str] = Field(default_factory=list, description="Imported Unity asset paths")
    instantiated_game_object: str | None = Field(default=None, description="Scene path of instantiated GameObject")
    instance_id: int | None = Field(default=None, description="Unity Instance ID")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking import warnings")


class ModelImporterInfo(BaseModel):
    """ModelImporter configuration details for imported 3D models."""

    animation_type: str = Field(default="None", description="Rig animation type: None, Legacy, Generic, Humanoid")
    clip_count: int = Field(default=0, description="Number of animation clips embedded in model")
    material_import_mode: str = Field(default="ImportViaMaterialDescription", description="Material import mode")
    import_normals: bool = Field(default=True, description="Whether normals are imported")
    global_scale: float = Field(default=1.0, description="Import scale factor")
    mesh_compression: str = Field(default="Off", description="Mesh compression level")


class InspectAssetResult(BaseToolResult):
    """Result schema for inspecting an asset and its import settings in Unity."""

    asset_path: str = Field(..., description="Queried Unity asset path")
    asset_type: str = Field(default="Unknown", description="Main asset type (e.g. Model, Texture2D, Material)")
    model_importer_info: ModelImporterInfo | None = Field(
        default=None, description="Rig and ModelImporter details if asset is 3D model"
    )
    submesh_count: int = Field(default=0, description="Number of submeshes detected")
    materials: list[str] = Field(default_factory=list, description="List of materials referenced by the asset")
    textures: list[str] = Field(default_factory=list, description="List of textures referenced by the asset")
    animation_clips: list[str] = Field(
        default_factory=list, description="Names of animation clips embedded in the model"
    )
    hierarchy_tree: list[str] = Field(default_factory=list, description="Hierarchy node names of the imported asset")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking inspection warnings")


class InstantiateSceneAssetResult(BaseToolResult):
    """Result schema for instantiating an asset into the active Unity scene."""

    game_object_name: str | None = Field(default=None, description="Name of the instantiated GameObject")
    game_object_path: str | None = Field(default=None, description="Full scene hierarchy path")
    instance_id: int | None = Field(default=None, description="Unity Instance ID")
    world_position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0], description="Position [x, y, z]")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings during instantiation")
