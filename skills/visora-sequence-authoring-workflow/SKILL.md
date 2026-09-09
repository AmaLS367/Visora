---
name: visora-sequence-authoring-workflow
description: Use when coordinating multi-track scenes, simultaneous character animations, camera trajectories, and keyframe events. Prescribes using atomic transactions, synchronized keyframe timing, and automated verification before committing.
---

## Visora sequence authoring workflow

Visora exposes high-level MCP tools for multi-track cinematic and gameplay sequence authoring:
`edit_animation_transaction`, `solve_camera_subject_contact`, and `preview_animation`.

Sequences involving multiple actors, camera paths, and VFX timing must be authored atomically
so that partial failures never leave scenes or assets in corrupted intermediate states.

---

### Golden rules

1. **Always wrap multi-operation edits in `edit_animation_transaction`.**
   Never execute disconnected single-keyframe writes across multiple clips. An atomic
   transaction guarantees automatic rollback to pre-mutation backups if any step fails.
2. **Synchronize animation events to kinetic turning points.**
   Footstep sounds, camera shakes, and VFX spawn events must match exact velocity peaks
   or contact timestamps identified via motion analysis.
3. **Always preserve non-destructive backups.**
   Confirm `backup_ids` are returned by transactions before proceeding to subsequent edits.
4. **Never finalize a sequence without previewing full multi-track playback.**
   Inspect the entire sequence through `preview_animation` in Edit Mode to confirm synchronization.

---

### Step-by-step sequence authoring sequence

#### 1. Define sequence beats and keyframe batch

Plan the atomic sequence operations across character and camera clips:
```python
edit_animation_transaction(
    description="Synchronize attack sequence impact and VFX event",
    operations=[
        {
            "operation_type": "set_keyframe",
            "clip_path": "Assets/Animations/Hero_Strike.anim",
            "target_path": "Characters/Hero/Hips",
            "type_name": "Transform",
            "property_name": "m_LocalPosition",
            "time": 0.45,
            "values": [0.0, 0.95, 0.40],
            "tangent_mode": "smooth",
        },
        {
            "operation_type": "set_keyframe_hold",
            "clip_path": "Assets/Animations/Hero_Strike.anim",
            "target_path": "Characters/Hero/Hips",
            "type_name": "Transform",
            "property_name": "m_LocalPosition",
            "start_time": 0.45,
            "duration": 0.08,
        },
        {
            "operation_type": "create_event",
            "clip_path": "Assets/Animations/Hero_Strike.anim",
            "time": 0.45,
            "function_name": "OnStrikeImpact",
            "string_parameter": "metal_clash",
            "float_parameter": 1.0,
            "int_parameter": 0,
        },
        {"operation_type": "ensure_continuity", "clip_path": "Assets/Animations/Hero_Strike.anim"},
    ],
)
```
Confirm `success == True` and `rollback_performed == False`.

#### 2. Verify sequence continuity & motion QA

Scan the modified sequence for curve flips or excessive jerk:
```python
detect_curve_discontinuities(clip_path="Assets/Animations/Hero_Strike.anim", auto_fix=True)
```

#### 3. Review final sequence playback

```python
preview_animation(
    clip_path="Assets/Animations/Hero_Strike.anim",
    target_object_path="Characters/Hero",
    camera_name="Main Camera",
    start_time=0.0,
    end_time=1.2,
    fps=30,
)
```
