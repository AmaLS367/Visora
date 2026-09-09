---
name: visora-motion-polish-workflow
description: Use before refining character animation timing, arcs of motion, anticipation, and follow-through. Prescribes applying the 12 principles of animation in 3D, smoothing joint jerk, and verifying natural kinetic spacing.
---

## Visora motion polish workflow

Visora exposes high-level MCP tools for polishing animation quality:
`analyze_joint_motion`, `list_animation_keyframes`, `edit_animation_transaction`,
`detect_curve_discontinuities`, and `preview_animation`.

Use this workflow to elevate animations from stiff mechanical poses to fluid,
believable character acting.

---

### Golden rules

1. **Motion travels in continuous arcs.**
   Natural organic limbs move along circular or parabolic arcs, never along sharp linear
   segments. Inspect curvature and velocity reversals with `analyze_joint_motion`.
2. **Every energetic action requires anticipation.**
   A high-speed punch, leap, or dash must be preceded by 2–4 frames of anticipation
   (e.g. crouching before a jump, pulling back a fist before a strike) to telegraph energy.
3. **Always cushion and settle after peak velocity.**
   Limbs cannot halt instantaneously from maximum speed. Follow impacts with 2–5 frames
   of overshoot, recoil, and damping before settling to a static pose.
4. **Never infer animation polish from a static screenshot.**
   Spacing, easing, and kinetic weight can only be judged across time via `preview_animation`.

---

### Step-by-step motion polish sequence

#### 1. Analyze velocity curves & jerk spikes

Identify sudden jarring stops and snapping keys:
```python
analyze_joint_motion(clip_path="Assets/Animations/Hero_Jump.anim", target_object_path="Characters/Hero", sample_fps=60)
```
Check `anomalies` for `jerk_spike` or `velocity_snap`.

#### 2. Shape keyframe tangents & spacing

Smooth out linear or sharp tangents around the turning points via `edit_animation_transaction`:
```python
edit_animation_transaction(
    description="Smooth jump arc tangents",
    operations=[
        {
            "operation_type": "set_keyframe",
            "clip_path": "Assets/Animations/Hero_Jump.anim",
            "target_path": "Characters/Hero/Hips",
            "type_name": "UnityEngine.Transform",
            "property_name": "m_LocalPosition",
            "time": 0.45,
            "values": [0.0, 1.2, 0.0],
            "tangent_mode": "smooth",
        }
    ],
)
```

#### 3. Establish hit-stop and anticipation holds

On powerful impact frames, insert a brief 2–4 frame hold via operation `set_keyframe_hold` to emphasize contact weight:
```python
edit_animation_transaction(
    description="Add impact hit-stop hold",
    operations=[
        {
            "operation_type": "set_keyframe_hold",
            "clip_path": "Assets/Animations/Hero_Jump.anim",
            "target_path": "Characters/Hero/Hips",
            "type_name": "UnityEngine.Transform",
            "property_name": "m_LocalPosition",
            "start_time": 0.45,
            "duration": 0.07,
        }
    ],
)
```

#### 4. Review motion across time

Verify the final polished timing in Edit Mode:
```python
preview_animation(
    target_object_path="Characters/Hero", clip_path="Assets/Animations/Hero_Jump.anim", auto_frame=True, fps=24
)
```
Check that the silhouette is readable and motion flows smoothly through impacts.
