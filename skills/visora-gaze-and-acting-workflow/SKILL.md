---
name: visora-gaze-and-acting-workflow
description: Use before authoring or modifying character gaze, head turns, or acting body language. Prescribes hierarchical gaze distribution across chest, neck, head, and eyes, anatomical limit verification, and natural posture evaluation.
---

## Visora gaze and acting workflow

Visora exposes high-level MCP tools for character orientation and acting:
`solve_character_gaze`, `preview_animation`, and `sample_animation_clip`.

Use this workflow whenever a character must look at the camera, track an opponent,
or react to a scene event with natural body language.

---

### Golden rules

1. **Never turn only the head bone.**
   Rotating only the head bone creates an unnatural "doll-head" or mannequin appearance.
   In natural acting, gaze is distributed across the entire upper body: Spine/Chest ($15\%$),
   Neck ($35\%$), Head ($50\%$), and Eyes.
2. **Never infer natural acting from a static screenshot.**
   A head angle that looks acceptable in a single static frame may appear robotic or snap
   unnaturally when animated. Always evaluate head and body turns across time via `preview_animation`.
3. **Respect anatomical joint limits.**
   Human necks and spines have strict angular limits (Neck yaw $\le 35^\circ$, Head yaw $\le 55^\circ$).
   Inspect `was_clamped` from `solve_character_gaze`. If the target requires more than $80^\circ$ of turn,
   the character's hips or root transform must turn to face the target.
4. **Stabilize up-vector posture.**
   Always maintain an upright head orientation relative to gravity or body forward; avoid excessive
   head roll (tilting) during horizontal turns unless deliberately acting groggy or curious.

---

### Step-by-step gaze & acting authoring sequence

#### 1. Test gaze solve in query mode

Check how the character's spine, neck, and head rotate towards the target:
```python
solve_character_gaze(
    target_object_path="Characters/Hero",
    target_transform_path="camera:Main Camera",
    chest_weight=0.15,
    neck_weight=0.35,
    head_weight=0.50,
    apply_to_scene=False,
)
```
Inspect:
- `total_target_angle_deg`: if $> 90^\circ$, character is turning towards something behind them.
- `was_clamped`: confirms whether joint limits were reached.
- `residual_gaze_error_deg`: check that the final line of sight reaches the target.

#### 2. Apply custom weight distribution for specific acting styles

Adjust weights depending on the acting intention:
- *Subtle casual eye glance:* `chest_weight=0.05`, `neck_weight=0.25`, `head_weight=0.70`.
- *Heavy, deliberate turn:* `chest_weight=0.30`, `neck_weight=0.40`, `head_weight=0.30`.
- *Alert combat readiness:* `chest_weight=0.20`, `neck_weight=0.35`, `head_weight=0.45`.

#### 3. Bake solved gaze to AnimationClip

Write keys to the animation clip at the key acting frame:
```python
solve_character_gaze(
    target_object_path="Characters/Hero",
    target_transform_path="camera:Main Camera",
    apply_to_scene=True,
    bake_to_clip="Assets/Animations/Hero_Look.anim",
    sample_time=1.25,
)
```
Verify `backup_id` is returned.

#### 4. Review motion across time

Render a lightweight preview to verify timing and natural settling:
```python
preview_animation(
    target_object_path="Characters/Hero", clip_path="Assets/Animations/Hero_Look.anim", auto_frame=True, fps=24
)
```
Check that the transition into and out of the look-at is smooth and does not snap.
