---
name: visora-contact-ik-workflow
description: Use before solving inverse kinematics, fixing limb sliding, or locking character effectors to targets or camera frames. Prescribes contact phase identification, limb chain verification, pole vector selection, reachability testing, and continuous curve baking.
---

## Visora contact IK workflow

Visora exposes high-level MCP tools for inverse kinematics and effector placement:
`solve_two_bone_ik`, `place_effector_in_viewport`, `analyze_contact_constraints`,
`bake_contact_constraints`, and `preview_animation`.

Use this workflow whenever a character must plant a foot on a surface, touch an object,
aim a hand, or make contact with a camera lens.

---

### Golden rules

1. **Never infer IK or contact success from a static screenshot.**
   A single frame screenshot cannot show whether a foot slides across frames, flips its knee
   backward, or snaps violently. Always verify motion across time via `preview_animation`.
2. **Verify reachability before baking.**
   Never force a limb past its maximum reach ($l_1 + l_2$). Always inspect `reach_distance`
   and `actual_distance` from `solve_two_bone_ik` to ensure the target is within reach
   ($\text{actual} \le 0.95 \cdot \text{reach}$) and avoid hyperextended knee/elbow pops.
3. **Always supply or verify the pole vector.**
   The pole vector controls which direction the elbow or knee folds. Without a stable pole vector,
   the bend plane can flip $180^\circ$ between frames when the limb is nearly straight.
4. **Enforce Edit Mode and non-destructive baking.**
   Never run IK baking in Play Mode. Ensure `bake_to_clip` creates a backup snapshot under
   `VisoraBackups/` before modifying curves, and check that `EnsureQuaternionContinuity` was applied.

---

### Step-by-step IK authoring & contact sequence

#### 1. Inspect limb chain and reachability

Test the limb kinematics in query mode without mutating the scene:
```python
solve_two_bone_ik(
    target_object_path="Characters/Hero",
    effector="left_foot",
    target_position=[0.2, 0.0, 0.5],
    pole_vector=[0.2, 0.5, 1.0],
    apply_to_scene=False,
)
```
Examine:
- `target_clamped`: if `True`, target is out of reach or in the soft-damping margin.
- `position_residual`: confirm residual error is near zero ($\le 0.01\text{m}$).
- `rotation_residual_deg`: check that the foot/hand orientation matches the target surface.

#### 2. Position effector in camera viewport (for action beats)

When aligning an impact, stomp, or grab directly with the camera:
```python
place_effector_in_viewport(
    target_object_path="Characters/Hero",
    effector="right_foot",
    camera_name="Main Camera",
    viewport_x=0.5,
    viewport_y=0.5,
    camera_depth=0.25,
    align_mode="face_camera",
    apply_to_scene=False,
)
```
Inspect:
- `screen_residual_pixels`: verifies foot center is on target on camera sensor.
- `is_clipped_by_near_plane`: ensures foot does not penetrate camera near clip.
- `is_in_frustum`: confirms foot is fully visible on screen.

#### 3. Bake solved pose to AnimationClip

Once target and pole vector are verified, bake keyframes into the clip:
```python
solve_two_bone_ik(
    target_object_path="Characters/Hero",
    effector="left_foot",
    target_position=[0.2, 0.0, 0.5],
    pole_vector=[0.2, 0.5, 1.0],
    apply_to_scene=True,
    bake_to_clip="Assets/Animations/Hero_Kick.anim",
    sample_time=0.45,
)
```
Confirm `backup_id` is returned.

#### 4. Review motion across time

Verify the baked clip with the smallest safe preview:
```python
preview_animation(
    target_object_path="Characters/Hero", clip_path="Assets/Animations/Hero_Kick.anim", auto_frame=True, fps=24
)
```
Check `motion_summary.is_static == False` and ensure no knee popping or sliding occurs.
