# Visora agent workflows

Visora is a typed MCP layer for Unity Editor diagnostics and safe scene work. Every tool returns a Pydantic result with `success` and, on failure, a concrete `error`; do not treat a missing image or payload as success.

## Transport

`legacy` is the default and uses AnkleBreaker. Set `UNITY_BRIDGE_MODE=native` only when `com.visora.editor` is installed. Native mode exposes typed camera endpoints and the same statement-body executor contract as legacy, so the MCP surface stays identical. `auto` supports both but prefers legacy when both are running.

## Tool catalog

An asterisk marks a required parameter. This region is generated from MCPServer registration; run `uv run -- python scripts/render_tool_catalog.py` after changing a tool.

<!-- GENERATED_TOOL_CATALOG_START -->
| Tool | Parameters | Result |
| --- | --- | --- |
| `analyze_animation_curves` | `clip_path`* | `ClipInspectorResult` |
| `check_ticket_status` | `ticket_id`* | `QueueStatusResult` |
| `clip_inspector` | `clip_path`* | `ClipInspectorResult` |
| `compare_screenshots` | `before_image_base64`*, `after_image_base64`*, `threshold` | `VisualComparisonResult` |
| `diagnose_camera_framing` | `subject_path`*, `camera_name` | `CameraFramingDiagnosticsResult` |
| `download_and_import_asset` | `url`, `asset_id`, `target_folder`, `file_name`, `extract_archive`, `allow_unitypackage`, `instantiate_in_scene`, `position`, `rotation`, `scale` | `DownloadAndImportAssetResult` |
| `find_bones` | `root_transform_path`*, `query`*, `exact_only`, `max_results` | `BoneSearchResult` |
| `get_bridge_status` | `scan_all_ports` | `BridgeStatusResult` |
| `get_editor_state` | `include_scene_details` | `EditorStateResult` |
| `get_video_frames` | `camera_names`, `subject_path`, `mode`, `clip_path`, `target_object_path`, `duration_seconds`, `fps`, `width`, `height`, `enter_play_mode`, `include_motion_metrics` | `VideoFramesResult` |
| `get_video_mp4` | `camera_name`, `subject_path`, `mode`, `clip_path`, `target_object_path`, `duration_seconds`, `fps`, `width`, `height`, `enter_play_mode` | `VideoMp4Result` |
| `import_local_asset` | `source_path`*, `target_folder`, `allow_unitypackage`, `instantiate_in_scene`, `position`, `rotation`, `scale` | `ImportLocalAssetResult` |
| `inspect_animation_clip` | `clip_path`* | `ClipInspectorResult` |
| `inspect_imported_asset` | `asset_path`* | `InspectAssetResult` |
| `inspect_scene_visual` | `subject_path`, `camera_name`, `width`, `height` | `VisualInspectionResult` |
| `instantiate_scene_asset` | `asset_path`*, `parent_path`, `position`, `rotation`, `scale`, `name` | `InstantiateSceneAssetResult` |
| `list_scene_cameras` | — | `ListSceneCamerasResult` |
| `playmode_management` | `play`*, `wait_for_idle`, `timeout_seconds` | `PlayModeManagementResult` |
| `project_world_points` | `points`*, `camera_name` | `ProjectWorldPointsResult` |
| `restore_scene_state` | `undo_group`, `reload_active_scene` | `RestoreSceneResult` |
| `safe_transaction` | `editor_code`*, `auto_save`, `record_undo`, `undo_name`, `restore_on_failure`, `timeout_seconds` | `SafeTransactionResult` |
| `sample_animation_clip` | `target_game_object_path`*, `clip_path`*, `time`, `normalized_time`, `restore_pose_after`, `track_transforms` | `SampleAnimationResult` |
| `save_scene` | `save_as_path`, `force_during_play_mode` | `SaveSceneResult` |
| `screenshot` | `camera_name`, `width`, `height` | `ScreenshotResult` |
| `search_assets` | `query`*, `category`, `source`, `limit`, `downloadable_only` | `SearchAssetsResult` |
| `skeleton_mapper` | `root_transform_path`* | `SkeletonMapperResult` |
| `skinned_mesh_diagnostics` | `mesh_renderer_path`* | `SkinnedMeshDiagnosticsResult` |
| `wait_for_editor_idle` | `timeout_seconds`, `poll_interval_seconds` | `WaitForEditorIdleResult` |
| `wait_for_ticket` | `ticket_id`*, `timeout`, `poll_interval` | `QueueStatusResult` |
| `web_search_assets` | `query`*, `limit` | `SearchAssetsResult` |
<!-- GENERATED_TOOL_CATALOG_END -->

## Reliable workflows

1. Call `get_bridge_status`, then `get_editor_state` before any editor mutation.
2. For visual issues, use `list_scene_cameras`, `diagnose_camera_framing`, then `screenshot` or `inspect_scene_visual`. Use `diagnostic_lit` captures to inspect model visibility; a dark game camera alone is not proof that the model is missing.
3. For rigs, call `skeleton_mapper`, `find_bones`, `inspect_animation_clip`, then `sample_animation_clip` with pose restoration enabled.
4. For mesh problems, call `skinned_mesh_diagnostics` before changing materials or bones; its category distinguishes geometry/skinning from texture/material failures.
5. For mutations, call `safe_transaction` with `record_undo=True`. If it fails, use its `undo_group` with `restore_scene_state` when necessary.
6. For asset discovery and imports, call `search_assets` to discover CC0 materials and 3D models online, `download_and_import_asset` to download and automatically register assets with the Unity `AssetDatabase`, `inspect_imported_asset` to verify `ModelImporter` rig settings, and `instantiate_scene_asset` to place them into the scene with Undo tracking. Sketchfab's own search endpoint ignores the query text (it behaves as a browse listing, not a real search, even with `SKETCHFAB_API_TOKEN` set) — for a specific model that `search_assets` can't find, call `web_search_assets` instead; it finds the real Sketchfab page via web search and returns a `sketchfab:<uid>` ready for `download_and_import_asset`.
7. When capturing video with `get_video_mp4` or `get_video_frames` with `enter_play_mode=True`, Visora actively polls and waits for domain reload and bridge re-binding before capturing frames, and safely restores Edit Mode on exit. When Domain Reload is enabled in Unity project settings, authored `AnimationClip` review can also be performed in Edit Mode using `sample_animation_clip` without domain reload overhead.

## Asset import safety

Asset files are first staged under `ASSET_CACHE_DIR`, which must be outside Unity's `Assets` folder. Supported imports are FBX, OBJ, glTF/GLB, PNG, JPG/JPEG, TGA, EXR, HDR, and ZIP archives containing only those files. The downloader accepts only public HTTPS hosts and validates every redirect.

Target folders are resolved inside `Assets`; path traversal is rejected. Existing files are never overwritten: Visora creates a suffixed filename and returns the exact resulting `asset_path` with a warning. A failed Unity import removes the newly copied asset and returns `success=false`.

Use a result's provider ID (for example, `sketchfab:<uid>`) as `asset_id` when no direct URL is present. `.unitypackage` files require `allow_unitypackage=true`; they remain quarantined until import and are rejected if their contents include scripts, assemblies, unsafe paths, or existing destination files.

## Scene safety

`save_scene` rejects Play Mode and compilation by default. `force_during_play_mode=True` is an intentional dangerous override; use it only when persistence of Play Mode state is explicitly required. `safe_transaction(auto_save=True)` skips automatic saves in Play Mode and reports this as a warning.

