---
name: visora-animation-workflow
description: Use before authoring, modifying, sampling, or previewing Unity AnimationClips on characters and objects. Prescribes rig/Avatar preflight, safe low-resolution Edit Mode preview iterations, contact constraint analysis, keyframe hold authoring, and final-quality capture criteria without risking scene corruption or inferring success from static screenshots.
---

## Visora animation workflow

Visora exposes high-level MCP tools for inspecting, sampling, modifying, and reviewing animations:
`inspect_animation_clip`, `analyze_animation_curves`, `sample_animation_clip`, `preview_animation`,
`list_animation_keyframes`, `set_animation_keyframe`, `move_animation_keyframe`, `remove_animation_keyframe`,
`set_keyframe_hold`, `create_animation_event`, `remove_animation_event`, `list_animation_backups`,
`restore_animation_clip`, `analyze_contact_constraints`, and `bake_contact_constraints`.

Every rule and sequence below is derived from live Unity testing to eliminate scene corruption,
domain-reload stalls, and false-positive verifications.

---

### Golden rules

1. **Never infer animation success from a static screenshot.**
   A character captured in a single screenshot might look perfect while being frozen in T-pose,
   sliding across the floor, or failing to play entirely. Always evaluate motion across time
   via `preview_animation` (checking `motion_summary.is_static` and `motion_intensity`).
2. **Start with the smallest safe preview.**
   Never start an animation check with high-resolution (1080p) or Play Mode video capture.
   Use lightweight Edit Mode previews (e.g. 320x240 or 480x360 at 12–24 fps) with `auto_frame=True`.
3. **Always preserve scene safety in Edit Mode.**
   Keep changes non-destructive. Never mutate or save the scene in Play Mode. When sampling poses
   with `sample_animation_clip`, always set `restore_pose_after=True` so temporary poses do not
   linger in the scene.
4. **Report concrete bridge and Unity failures directly.**
   If a tool fails (`success=false`), inspect and report `error` and `warnings` explicitly.
   Do not mask errors or assume success.

---

### Step-by-step authoring & review sequence

#### 1. Preflight rig & clip

Before modifying curves or sampling:
- **Editor state:** Call `get_editor_state()` to confirm the editor is in Edit Mode and idle.
- **Hierarchy & Rig:** Call `skeleton_mapper(root_transform_path=...)` or `find_bones` to verify the
  target GameObject has the necessary bone hierarchy and an `Animator` or `Animation` component.
- **Clip diagnostics:** Call `inspect_animation_clip(clip_path=...)` or `analyze_animation_curves(clip_path=...)`.
  Examine:
  - `duration` and `frame_rate`;
  - `bindings`: check whether curves bind to `UnityEngine.Transform` (Generic rig) or
    `UnityEngine.Animator` / muscle curves (Humanoid);
  - `events`: note existing animation events.

#### 2. Fast iteration loop (The small safe preview)

Do not trigger heavy renders or Play Mode domain reloads for intermediate checks.
- Call `preview_animation`:
  ```python
  preview_animation(
      target_object_path="Characters/Hero",
      clip_path="Assets/Animations/Run.anim",
      width=320,
      height=240,
      fps=12,
      auto_frame=True,
      max_key_frames=6,
  )
  ```
- **Inspect motion metrics:**
  - If `motion_summary.is_static` is `True`, the clip is **not** animating the target (e.g. bone
    path mismatch, missing avatar, or zero-delta curves). Investigate bindings before doing visual review.
  - Review the timestamped `key_frames` to observe extreme poses, peak energy timestamps, and inflection points.
- If you need to inspect a specific pose at time $t$, call:
  ```python
  sample_animation_clip(
      target_game_object_path="Characters/Hero",
      clip_path="Assets/Animations/Run.anim",
      time=t,
      restore_pose_after=True,
  )
  ```

#### 3. Contact dynamics & foot sliding checks

For character locomotion, combat, or ground interactions:
- Call `analyze_contact_constraints`:
  ```python
  analyze_contact_constraints(
      target_object_path="Characters/Hero",
      clip_path="Assets/Animations/Run.anim",
      ground_mode="plane",
      ground_plane_y=0.0,
  )
  ```
- Check `anomalies` for:
  - `foot_sliding`: horizontal drift during stance phases exceeding `velocity_threshold`;
  - `ground_penetration`: feet passing beneath `ground_plane_y`;
  - `floating`: feet failing to reach contact elevation.
- If sliding or penetration is detected:
  - Call `bake_contact_constraints(clip_path=..., target_object_path=..., fix_foot_sliding=True, fix_penetration=True)`.
  - Visora automatically creates a snapshot under `Assets/VisoraBackups/` before mutating the clip.
  - Check `backup_id` in the result so you can call `restore_animation_clip` if rollback is needed.

#### 4. Curve, hold, and event authoring

When adjusting animation curves or timing:
- **Inspect keys:** Call `list_animation_keyframes(clip_path=..., target_path=..., type_name=..., property_name=...)`.
- **Modify timing:** Call `move_animation_keyframe` or `set_animation_keyframe` with `operation_id` for idempotency.
- **Hold poses / Hit-stop:** To lock a pose during an impact without altering surrounding curves,
  call `set_keyframe_hold(clip_path=..., target_path=..., type_name=..., property_name=..., time=start_t, hold_until=end_t)`.
- **Author events:** Call `create_animation_event(clip_path=..., time=t, function_name=...)`.
- **Verify backups:** Call `list_animation_backups(clip_path=...)` to confirm snapshots are retained.

#### 5. Final-quality capture criteria

Only advance to final recording when the low-resolution iterations pass motion, contact, and framing checks.
- Set resolution and framerate to production values (e.g. `width=640`, `height=360`, `fps=24` or `fps=30`).
- Call `preview_animation` or `get_video_mp4`:
  - Verify `actual_fps` matches the requested frame rate.
  - Confirm `timing_source` indicates dependable timing (e.g. `authored_clip` or Unity frame clock).
  - Check `rendered_camera_name` to ensure framing remained centered on the subject.
