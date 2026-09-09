---
name: visora-camera-contact-workflow
description: Use before authoring or adjusting high-impact character-camera interactions, drops, stomps, or lens strikes. Prescribes aligning effectors directly to the camera viewport, authoring synchronized hit-stops and recoil impulses, and verifying dynamic composition across time.
---

## Visora camera contact workflow

Visora exposes dedicated MCP tools for high-impact cinematic action:
`solve_camera_subject_contact`, `bake_effector_contact`, `place_effector_in_viewport`,
`edit_animation_transaction`, `preview_animation`, and `diagnose_camera_framing`.

Cinematic impacts (e.g. dropkick into the lens, ground pound shockwave, monster grab)
fall flat if character motion and camera reaction are authored separately. Always solve
them synchronously.

---

### Golden rules

1. **Every impact requires an authoritative timestamp $T_{\text{impact}}$.**
   Character contact, hit-stop holds, camera recoil, and animation events must all anchor
   to the exact same frame timestamp.
2. **Never add unsynchronized procedural camera shake.**
   Procedural shake that starts before impact or drifts out of sync destroys kinetic weight.
   Anchor recoil impulses directly at $T_{\text{impact}}$.
3. **Always freeze the action on peak impact (hit-stop).**
   Insert 2–4 frames (0.05–0.08s) of keyframe hold on both character and camera to give
   the audience's eye time to register the collision.
4. **Never infer impact synchronization from a static screenshot.**
   Always inspect the kinetic energy transfer across time using `preview_animation`.

---

### Step-by-step camera contact sequence

#### 1. Frame the impact target in viewport space

Determine the impact composition. A direct lens kick targets the center `[0.5, 0.5]` at
close depth ($Z \approx 0.25\text{m} - 0.35\text{m}$):
```python
place_effector_in_viewport(
    camera_name="Main Camera",
    target_object_path="Characters/Hero",
    effector="right_foot",
    viewport_x=0.5,
    viewport_y=0.5,
    camera_depth=0.30,
    align_mode="align_sole",
    apply_to_scene=False,
)
```
Check `reach_distance` and `actual_distance` to confirm limb reachability ($< 0.95$).

#### 2. Solve coordinated impact and camera recoil

Execute composite character limb lock and camera impulse authoring:
```python
solve_camera_subject_contact(
    character_path="Characters/Hero",
    character_clip_path="Assets/Animations/Hero_Dropkick.anim",
    camera_name="Main Camera",
    camera_clip_path="Assets/Animations/Camera_Action.anim",
    effector="right_foot",
    impact_time=0.62,
    contact_duration=0.18,
    lens_viewport=[0.5, 0.5],
    lens_distance_meters=0.28,
    hit_stop_duration=0.08,
    camera_recoil_impulse=[0.0, -0.25, -0.50],
)
```
Confirm:
- `character_backup_id` and `camera_backup_id` are recorded.
- `impact_screen_residual_pixels` is $< 5.0$ pixels.
- `max_limb_reach_ratio` is $\le 0.98$.

#### 3. Verify kinetic impact preview

Generate a preview sequence across the impact window:
```python
preview_animation(
    clip_path="Assets/Animations/Hero_Dropkick.anim",
    target_object_path="Characters/Hero",
    camera_name="Main Camera",
    start_time=0.45,
    end_time=1.10,
    fps=30,
)
```
Verify that the limb hits the lens exactly at $T_{\text{impact}}$, holds during the hit-stop,
and recoils naturally.
