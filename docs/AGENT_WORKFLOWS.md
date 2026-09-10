# Visora agent workflows

Visora is a typed MCP layer for Unity Editor diagnostics and safe scene work. Every tool returns a Pydantic result with `success` and, on failure, a concrete `error`; do not treat a missing image or payload as success.

<p align="center">
  <img src="assets/concepts-workflow.jpg" alt="The Visora workflow cycles through inspection, safe action, and evidence-based verification around a Unity scene" width="100%">
</p>
<p align="center"><em>Start with evidence, make one recoverable change, then verify the same scene over time.</em></p>

## Transport

`legacy` is the default and uses AnkleBreaker. Set `UNITY_BRIDGE_MODE=native` only when `com.visora.editor` is installed. Native mode exposes typed camera endpoints and the same statement-body executor contract as legacy, so the MCP surface stays identical. `auto` supports both but prefers legacy when both are running.

## Tool catalog

An asterisk marks a required parameter. This region is generated from MCPServer registration; run `uv run -- python scripts/render_tool_catalog.py` after changing a tool.

<!-- GENERATED_TOOL_CATALOG_START -->
| Tool | Parameters | Result |
| --- | --- | --- |
| `analyze_contact_constraints` | `target_object_path`*, `clip_path`*, `effectors`, `ground_mode`, `ground_plane_y`, `velocity_threshold`, `height_tolerance` | `ContactAnalysisResult` |
| `analyze_joint_motion` | `clip_path`*, `target_object_path`*, `bones`, `sample_fps`, `jerk_threshold`, `angular_jerk_threshold` | `JointMotionAnalysisResult` |
| `analyze_self_intersections` | `target_object_path`*, `clip_path`*, `sample_fps`, `tolerance_meters` | `SelfIntersectionResult` |
| `bake_contact_constraints` | `clip_path`*, `target_object_path`*, `output_clip_path`, `effectors`, `ground_plane_y`, `fix_foot_sliding`, `fix_penetration`, `operation_id` | `BakeContactConstraintsResult` |
| `bake_effector_contact` | `clip_path`*, `target_object_path`*, `effector`*, `target_type`, `target_position`, `scene_object_path`, `camera_name`, `viewport_coordinates`, `viewport_depth`, `time_range`, `blend_in_seconds`, `blend_out_seconds`, `pole_vector`, `target_rotation` | `BakeEffectorContactResult` |
| `capture_video` | `output`, `camera_names`, `subject_path`, `mode`, `clip_path`, `target_object_path`, `duration_seconds`, `fps`, `width`, `height`, `enter_play_mode`, `include_motion_metrics`, `include_video_base64` | `BaseToolResult` |
| `check_ticket_status` | `ticket_id`*, `wait`, `timeout_seconds`, `poll_interval_seconds` | `QueueStatusResult` |
| `compare_animation_previews` | `baseline_preview_id`*, `comparison_preview_id`*, `baseline_slide_distance`, `comparison_slide_distance`, `baseline_peak_jerk`, `comparison_peak_jerk`, `baseline_peak_speed`, `comparison_peak_speed`, `baseline_camera_distance`, `comparison_camera_distance`, `keyframes_diff_count` | `BaseToolResult` |
| `compare_screenshots` | `before_image_path`*, `after_image_path`*, `threshold` | `BaseToolResult` |
| `configure_humanoid_avatar` | `asset_path`*, `bone_mapping_overrides`, `source_avatar_path` | `HumanoidConfigurationResult` |
| `detect_curve_discontinuities` | `clip_path`*, `filter_curves`, `auto_fix` | `CurveDiscontinuityResult` |
| `diagnose_camera_framing` | `subject_path`*, `camera_name` | `CameraFramingDiagnosticsResult` |
| `download_and_import_asset` | `url`, `asset_id`, `target_folder`, `file_name`, `extract_archive`, `allow_unitypackage`, `instantiate_in_scene`, `position`, `rotation`, `scale` | `DownloadAndImportAssetResult` |
| `edit_animation_transaction` | `operations`*, `transaction_id`, `description` | `AnimationTransactionResult` |
| `find_bones` | `root_transform_path`*, `query`*, `exact_only`, `max_results` | `BoneSearchResult` |
| `get_animation_preview_record` | `preview_id`* | `AnimationPreviewRecordResult` |
| `get_bridge_status` | `scan_all_ports` | `BridgeStatusResult` |
| `get_editor_state` | `include_scene_details`, `wait`, `timeout_seconds`, `poll_interval_seconds` | `EditorStateResult` |
| `import_local_asset` | `source_path`*, `target_folder`, `allow_unitypackage`, `instantiate_in_scene`, `position`, `rotation`, `scale` | `ImportLocalAssetResult` |
| `inspect_animation_clip` | `clip_path`*, `path_filter`, `max_bindings` | `ClipInspectorResult` |
| `inspect_imported_asset` | `asset_path`*, `max_hierarchy_nodes` | `InspectAssetResult` |
| `inspect_scene_visual` | `subject_path`, `camera_name`, `width`, `height` | `BaseToolResult` |
| `instantiate_scene_asset` | `asset_path`*, `parent_path`, `position`, `rotation`, `scale`, `name` | `InstantiateSceneAssetResult` |
| `list_animation_backups` | `clip_path`* | `ListAnimationBackupsResult` |
| `list_animation_keyframes` | `clip_path`*, `target_path`*, `type_name`*, `property_name`* | `ListAnimationKeyframesResult` |
| `list_animation_preview_records` | `clip_path`, `target_object_path`, `limit` | `AnimationPreviewListResult` |
| `list_scene_cameras` | — | `ListSceneCamerasResult` |
| `place_effector_in_viewport` | `target_object_path`*, `viewport_x`, `viewport_y`, `camera_depth`, `camera_name`, `effector`, `root_bone`, `mid_bone`, `end_bone`, `align_mode`, `custom_rotation`, `pole_vector`, `weight`, `apply_to_scene`, `bake_to_clip`, `sample_time` | `ViewportEffectorPlacementResult` |
| `playmode_management` | `play`*, `wait_for_idle`, `timeout_seconds` | `PlayModeManagementResult` |
| `preview_animation` | `target_object_path`*, `clip_path`*, `camera_name`, `start_time`, `end_time`, `fps`, `width`, `height`, `auto_frame`, `max_key_frames`, `include_video_base64`, `include_clip_diagnostics` | `BaseToolResult` |
| `preview_humanoid_retarget` | `target_object_path`*, `clip_path`*, `camera_name`, `width`, `height`, `fps`, `auto_frame` | `HumanoidRetargetPreviewResult` |
| `project_world_points` | `points`*, `camera_name` | `ProjectWorldPointsResult` |
| `restore_animation_clip` | `clip_path`*, `backup_id`*, `operation_id` | `RestoreAnimationClipResult` |
| `restore_scene_state` | `undo_group`, `reload_active_scene` | `RestoreSceneResult` |
| `safe_transaction` | `editor_code`*, `auto_save`, `record_undo`, `undo_name`, `restore_on_failure`, `timeout_seconds` | `SafeTransactionResult` |
| `sample_animation_clip` | `target_game_object_path`*, `clip_path`*, `time`, `normalized_time`, `restore_pose_after`, `track_transforms`, `max_transforms` | `SampleAnimationResult` |
| `save_scene` | `save_as_path`, `force_during_play_mode` | `SaveSceneResult` |
| `screenshot` | `camera_name`, `width`, `height` | `BaseToolResult` |
| `search_assets` | `query`*, `category`, `source`, `limit`, `downloadable_only` | `SearchAssetsResult` |
| `skeleton_mapper` | `root_transform_path`*, `max_bones` | `SkeletonMapperResult` |
| `skinned_mesh_diagnostics` | `mesh_renderer_path`*, `max_bone_bindings` | `SkinnedMeshDiagnosticsResult` |
| `solve_camera_subject_contact` | `character_path`*, `character_clip_path`*, `camera_name`*, `camera_clip_path`, `effector`, `impact_time`, `contact_duration`, `lens_viewport`, `lens_distance_meters`, `hit_stop_duration`, `camera_recoil_impulse` | `CameraSubjectContactResult` |
| `solve_character_gaze` | `target_object_path`*, `target_look_at_position`, `target_transform_path`, `chest_weight`, `neck_weight`, `head_weight`, `eyes_weight`, `up_vector`, `apply_to_scene`, `bake_to_clip`, `sample_time` | `CharacterGazeResult` |
| `solve_two_bone_ik` | `target_object_path`*, `target_position`*, `effector`, `root_bone`, `mid_bone`, `end_bone`, `target_rotation`, `pole_vector`, `space`, `camera_name`, `weight`, `apply_to_scene`, `bake_to_clip`, `sample_time` | `TwoBoneIKSolveResult` |
| `validate_humanoid_avatar` | `target_path`, `asset_path` | `HumanoidValidationResult` |
| `web_search_assets` | `query`*, `limit` | `SearchAssetsResult` |
<!-- GENERATED_TOOL_CATALOG_END -->

## Reliable workflows

1. Call `get_bridge_status`, then `get_editor_state` before any editor mutation.
2. For visual issues, use `list_scene_cameras`, `diagnose_camera_framing`, then `screenshot` or `inspect_scene_visual`. Use `diagnostic_lit` captures to inspect model visibility; a dark game camera alone is not proof that the model is missing.
3. For rigs, call `skeleton_mapper`, `find_bones`, `inspect_animation_clip`, then `sample_animation_clip` with pose restoration enabled.
4. For mesh problems, call `skinned_mesh_diagnostics` before changing materials or bones; its category distinguishes geometry/skinning from texture/material failures.
5. For mutations, call `safe_transaction` with `record_undo=True`. If it fails, use its `undo_group` with `restore_scene_state` when necessary.
6. For asset discovery and imports, call `search_assets` to discover CC0 materials and 3D models online, `download_and_import_asset` to download and automatically register assets with the Unity `AssetDatabase`, `inspect_imported_asset` to verify `ModelImporter` rig settings, and `instantiate_scene_asset` to place them into the scene with Undo tracking. Sketchfab's own search endpoint ignores the query text (it behaves as a browse listing, not a real search, even with `SKETCHFAB_API_TOKEN` set) — for a specific model that `search_assets` can't find, call `web_search_assets` instead; it finds the real Sketchfab page via web search and returns a `sketchfab:<uid>` ready for `download_and_import_asset`.
7. When capturing video with `capture_video` with `enter_play_mode=True`, Visora actively polls and waits for domain reload and bridge re-binding before capturing frames, and safely restores Edit Mode on exit. When Domain Reload is enabled in Unity project settings, authored `AnimationClip` review can also be performed in Edit Mode using `sample_animation_clip` without domain reload overhead.
8. For animation authoring and review (`skills/visora-animation-workflow`), preflight the rig with `get_editor_state`, `skeleton_mapper`, and `inspect_animation_clip`. Always iterate with lightweight Edit Mode `preview_animation` (e.g. 320x240 @ 12–24 fps) before any final capture; never infer animation success from a static screenshot (`motion_summary.is_static` must be false). Verify contacts with `analyze_contact_constraints` and bake IK fixes non-destructively via `bake_contact_constraints`.
9. For combat and camera action timing (`skills/visora-camera-action-workflow`), establish a single authoritative impact timestamp $T_{\text{impact}}$. Synchronize character hit-stop (via `edit_animation_transaction` with `set_keyframe_hold`), directional camera recoil impulse, and event triggers (via `create_event`) to that exact instant. Do not rely on unsynchronized procedural screen shake as the default, and verify viewport framing with `diagnose_camera_framing` and `project_world_points`.
10. For character rigs and mocap retargeting (`skills/visora-rig-retarget-workflow`), inspect the hierarchy with `skeleton_mapper` and preflight Humanoid Avatar eligibility with `validate_humanoid_avatar`. For eligible rigs, configure mappings with `configure_humanoid_avatar` and preview retargeted motion across time with `preview_humanoid_retarget`. If the rig has fatal blockers (quadrupeds, mechanical models, non-bipedal structures), never force Humanoid mode; retain Generic and use skeleton-matched Transform curves.

## Asset import safety

Asset files are first staged under `ASSET_CACHE_DIR`, which must be outside Unity's `Assets` folder. Supported imports are FBX, OBJ, glTF/GLB, PNG, JPG/JPEG, TGA, EXR, HDR, and ZIP archives containing only those files. The downloader accepts only public HTTPS hosts and validates every redirect.

Target folders are resolved inside `Assets`; path traversal is rejected. Existing files are never overwritten: Visora creates a suffixed filename and returns the exact resulting `asset_path` with a warning. A failed Unity import removes the newly copied asset and returns `success=false`.

Use a result's provider ID (for example, `sketchfab:<uid>`) as `asset_id` when no direct URL is present. `.unitypackage` files require `allow_unitypackage=true`; they remain quarantined until import and are rejected if their contents include scripts, assemblies, unsafe paths, or existing destination files.

## Scene safety

`save_scene` rejects Play Mode and compilation by default. `force_during_play_mode=True` is an intentional dangerous override; use it only when persistence of Play Mode state is explicitly required. `safe_transaction(auto_save=True)` skips automatic saves in Play Mode and reports this as a warning.
