# 🤖 Visora Agent Workflows & Tool Recipes

> Canonical guide to the 46 MCP tools, transport modes, and safe sequence recipes for AI agents operating inside Unity Editor.

Visora is a typed MCP layer for Unity Editor diagnostics, character rigging, animation analysis, and safe scene operations. Every tool returns a structured Pydantic model with `success` and, on failure, an actionable `error`.

<p align="center">
  <img src="assets/concepts-workflow.jpg" alt="The Visora workflow cycles through inspection, safe action, and evidence-based verification around a Unity scene" width="100%">
</p>
<p align="center"><em>Start with evidence, make one recoverable change, then verify the same scene over time.</em></p>

---

## 🔌 Transport Modes & Bridge Selection

- **Legacy Mode (`UNITY_BRIDGE_MODE=legacy`)**: Default mode. Connects to an existing AnkleBreaker bridge over HTTP. Executes compatible operations through centralized C# statement bodies.
- **Native Mode (`UNITY_BRIDGE_MODE=native`)**: Connects to the high-performance `com.visora.editor` package in Unity 6+. Exposes dedicated endpoints for camera rendering, animation inspection, and main-thread transactions.
- **Auto Mode (`UNITY_BRIDGE_MODE=auto`)**: Discovers both bridges and prefers legacy if both are active.

> [!TIP]
> Both bridge modes expose the exact same typed MCP tools and schemas to the agent, preserving consistent tool interactions.

---

## 📋 Tool Catalog

An asterisk (`*`) denotes a required parameter.

> [!NOTE]
> This catalog table is automatically synchronized from MCPServer registration via `uv run python scripts/render_tool_catalog.py`.


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

## 🎯 Reliable Workflow Recipes

### 1️⃣ Baseline State Preflight
Always verify Unity Editor connectivity and idle state before attempting scene mutations:
- Call `get_bridge_status` to ensure bridge health, low latency, and correct active port.
- Call `get_editor_state` to verify `is_idle=true` and confirm the active scene.

### 2️⃣ Visual Inspection & Framing
Isolate lighting issues from missing geometry:
- Call `list_scene_cameras` to find all available cameras.
- Call `diagnose_camera_framing` to calculate target bounding boxes and viewport coverage.
- Call `inspect_scene_visual` for a neutral diagnostic-lit render (`diagnostic_lit`); a dark game camera alone does **not** prove an object is missing.

### 3️⃣ Rig & Bone Inspection
Examine character skeletons non-destructively:
- Call `skeleton_mapper` to map the full transform hierarchy.
- Call `find_bones` to locate specific joints (e.g. `head`, `hand`, `foot`).
- Call `inspect_animation_clip` and `sample_animation_clip` with `restore_pose_after=true` to preview poses safely.

### 4️⃣ Skinned Mesh Diagnostics
Diagnose character deformation issues systematically:
- Call `skinned_mesh_diagnostics` before altering materials or bone transforms.
- Its diagnostic categorization reliably distinguishes geometry/skinning weight issues from texture/shader failures.

### 5️⃣ Scoped Mutations & Atomic Undo
Execute editor modifications within safe boundaries:
- Wrap operations in `safe_transaction` with `record_undo=true`.
- If an execution fails, use the returned `undo_group` with `restore_scene_state` to roll back changes cleanly.

### 6️⃣ 3D Asset Discovery & Ingestion
Download, quarantine, and instantiate 3D assets securely:
- Discover assets using `search_assets` (Poly Pizza / Sketchfab).
- For specific models where Sketchfab's browse API fails, use `web_search_assets` to locate the model page and obtain a `sketchfab:<uid>`.
- Download and register via `download_and_import_asset`.
- Verify the imported hierarchy and materials with `inspect_imported_asset`.
- Place into the active scene with Undo tracking via `instantiate_scene_asset`.

### 7️⃣ Video Capture & Domain Reload Recovery
Capture high-fidelity gameplay or Edit Mode timelines:
- Call `capture_video` with `enter_play_mode=true`; Visora polls and waits for domain reload and bridge re-binding before capturing frames, restoring Edit Mode on completion.
- When Domain Reload is enabled in project settings, authored clips can also be reviewed in Edit Mode using `sample_animation_clip` without domain reload overhead.

### 8️⃣ Animation Review & Contact IK Baking
Iterate on character motion with motion metrics:
- Preflight the rig with `get_editor_state`, `skeleton_mapper`, and `inspect_animation_clip`.
- Iterate rapidly with lightweight Edit Mode `preview_animation` (e.g. 320×240 @ 12–24 fps). Never infer animation success from a static screenshot (`motion_summary.is_static` must be `false`).
- Detect sliding feet with `analyze_contact_constraints` and bake fixes non-destructively with `bake_contact_constraints`.

### 9️⃣ Combat Hit-Stops & Camera Action Timing
Coordinate dynamic character-camera interactions:
- Establish a single authoritative impact timestamp $T_{\text{impact}}$.
- Synchronize character hit-stop (`edit_animation_transaction` with `set_keyframe_hold`), directional camera recoil impulse, and event triggers to that exact instant.
- Verify camera framing across time with `diagnose_camera_framing` and `project_world_points`.

### 🔟 Character Rig & Mocap Retargeting
Verify and configure humanoid avatars:
- Inspect hierarchy with `skeleton_mapper` and preflight Humanoid eligibility with `validate_humanoid_avatar`.
- Configure bone mappings with `configure_humanoid_avatar` and preview retargeted motion across time with `preview_humanoid_retarget`.
- If a rig has fatal blockers (quadrupeds, mechanical models), never force Humanoid mode; retain Generic and use skeleton-matched transform curves.

---

## 📦 Asset Import Safety Rules

> [!IMPORTANT]
> **Quarantine Staging**: Downloaded assets are staged in `ASSET_CACHE_DIR` (outside the Unity `Assets/` directory). Only validated assets are copied into the project.

- **Supported Formats**: FBX, OBJ, glTF/GLB, PNG, JPG/JPEG, TGA, EXR, HDR, and ZIP archives containing only these formats.
- **SSRF & Path Traversal**: Downloader strictly requires public HTTPS schemes and rejects private IP ranges and path traversals (`../`).
- **Collision Protection**: Existing assets are never overwritten; a suffixed filename is generated, and the actual `asset_path` is returned with a warning.
- **`.unitypackage` Quarantine**: Requires `allow_unitypackage=true`. Quarantined until validated; rejected if containing scripts, native DLLs, or unsafe target paths.

---

## 🛡️ Scene Safety Invariants

> [!CAUTION]
> **Play Mode Protection**: `save_scene` rejects saving during Play Mode and active script compilation by default. `force_during_play_mode=true` is a dangerous override that should only be used when explicitly required.

> [!NOTE]
> `safe_transaction(auto_save=true)` automatically skips disk saving if executed while Unity is in Play Mode, returning a diagnostic warning.

