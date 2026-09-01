from typing import Any

from pydantic import Field

from backend.schemas.base import BaseToolResult


class EditorStateResult(BaseToolResult):
    """Result schema for inspecting Unity editor runtime and compilation state."""

    is_playing: bool = Field(default=False, description="Whether Unity is currently in Play Mode")
    is_paused: bool = Field(default=False, description="Whether Unity Play Mode is currently paused")
    is_compiling: bool = Field(default=False, description="Whether Unity is currently compiling scripts")
    is_updating: bool = Field(default=False, description="Whether Unity editor is currently updating/busy")
    is_idle: bool = Field(default=True, description="True if Unity is not compiling and not updating")
    active_scene_name: str | None = Field(default=None, description="Name of the currently active scene")
    active_scene_path: str | None = Field(default=None, description="Asset path of the currently active scene")
    active_scene_dirty: bool | None = Field(default=None, description="Whether the active scene has unsaved changes")
    loaded_scene_count: int = Field(default=0, description="Number of currently loaded scenes")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking editor state warnings")


class WaitForEditorIdleResult(BaseToolResult):
    """Result schema for waiting until the Unity Editor reaches an idle state."""

    is_idle: bool = Field(default=False, description="True if the editor reached idle before timeout")
    waited_seconds: float = Field(default=0.0, description="Total seconds spent waiting")
    is_compiling: bool = Field(default=False, description="Final compilation status")
    is_updating: bool = Field(default=False, description="Final updating status")
    is_playing: bool = Field(default=False, description="Final playmode status")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings during wait")
    message: str = Field(..., description="Status message detailing the wait outcome")


class PlayModeManagementResult(BaseToolResult):
    """Result schema for playmode state changes."""

    is_playing: bool = Field(..., description="Current playmode state after the tool execution")
    is_paused: bool = Field(default=False, description="Whether play mode is currently paused")
    previous_state: bool = Field(..., description="Previous playmode state prior to the tool execution")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking playmode warnings")
    message: str = Field(..., description="Status message detailing the playmode state change")


class SaveSceneResult(BaseToolResult):
    """Result schema for safe scene saving."""

    scene_name: str | None = Field(default=None, description="Name of the saved scene")
    scene_path: str | None = Field(default=None, description="Asset path of the saved scene")
    was_dirty: bool = Field(default=False, description="Whether the scene had unsaved changes prior to saving")
    is_saved: bool = Field(default=False, description="Whether the scene was successfully saved to disk")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking save warnings (e.g. playmode warnings)")
    message: str = Field(..., description="Status message detailing the save outcome")


class SafeTransactionResult(BaseToolResult):
    """Result schema for safe editor transaction operations."""

    transaction_id: str = Field(..., description="Unique identifier for the transaction")
    scene_saved: bool = Field(default=False, description="Whether the active scene was saved")
    undo_group: int | None = Field(default=None, description="Unity Undo group index for this transaction")
    rolled_back: bool = Field(default=False, description="Whether changes were rolled back due to error")
    execution_result: Any | None = Field(default=None, description="Returned value from executed editor code")
    logs: list[str] = Field(default_factory=list, description="Logs captured during editor code execution")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking transaction warnings")
    message: str = Field(..., description="Status message detailing the outcome of the transaction")


class RestoreSceneResult(BaseToolResult):
    """Result schema for restoring scene or undo state."""

    reverted_undo: bool = Field(default=False, description="Whether an Undo group was reverted")
    reloaded_scene: bool = Field(default=False, description="Whether the active scene was reloaded from disk")
    active_scene_name: str | None = Field(default=None, description="Name of the active scene after restore")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking restore warnings")
    message: str = Field(..., description="Status message detailing the restore outcome")
