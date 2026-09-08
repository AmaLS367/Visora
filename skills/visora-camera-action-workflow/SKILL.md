---
name: visora-camera-action-workflow
description: Use when orchestrating impact moments, combat beats, hits, and camera reactions in Unity. Prescribes establishing a single authoritative impact timestamp, synchronizing character pose freeze/hold, camera recoil, flash/VFX events, and hit-stop, and forbids unsynchronized procedural screen shake as the default.
---

## Visora camera action workflow

Visora exposes tools for orchestrating and verifying tight action timing in Unity:
`inspect_animation_clip`, `sample_animation_clip`, `preview_animation`, `list_animation_keyframes`,
`set_animation_keyframe`, `set_keyframe_hold`, `create_animation_event`, `list_scene_cameras`,
`diagnose_camera_framing`, `project_world_points`, and `get_video_mp4`.

This workflow defines the standard for combat impacts, explosions, parries, and cinematic beats.

---

### Core principles

1. **One authoritative impact timestamp ($T_{\text{impact}}$).**
   Never allow procedural effects, particle systems, camera shakes, and animation poses to trigger on
   independent timers. Every reaction must anchor strictly to a single authoritative timestamp
   $T_{\text{impact}}$ determined from the animation clip.
2. **No unsynchronized procedural camera shake as default.**
   Continuous, random procedural screen shake obscures animation quality and disconnects impact from
   cause. Camera response must be an intentional directional recoil impulse starting at $T_{\text{impact}}$,
   settling back to the resting camera pose within 0.1–0.3 seconds.
3. **Never infer impact synchronization from a static screenshot.**
   A screenshot at $T_{\text{impact}}$ only shows a single still frame; it cannot verify whether
   hit-stop was held, whether the camera impulse had proper recovery, or whether events fired at the
   correct instant. Always preview the motion window across time.
4. **Report concrete bridge and Unity errors.**
   If camera projection or clip mutation returns `success=false`, report the explicit error and stop
   before attempting subsequent synchronized edits.

---

### Step-by-step action synchronization sequence

#### 1. Establish the authoritative impact timestamp ($T_{\text{impact}}$)

- Inspect the combat clip using `inspect_animation_clip(clip_path=...)`.
- If the exact impact frame is not known, run a lightweight windowed preview or sample poses:
  ```python
  preview_animation(
      target_object_path="Characters/Attacker",
      clip_path="Assets/Animations/HeavyPunch.anim",
      width=320,
      height=240,
      fps=24,
      auto_frame=True,
  )
  ```
- Inspect `key_frames` and find the frame where the limb or weapon reaches full extension / contact.
  Record this exact timestamp as $T_{\text{impact}}$ (e.g. `0.458` s).

#### 2. Apply hit-stop (Keyframe hold)

A satisfying impact requires physical weight: the attacker and victim momentarily freeze upon contact.
- Lock the character pose at $T_{\text{impact}}$ for 2 to 6 frames (typically 0.05 to 0.12 seconds):
  ```python
  set_keyframe_hold(
      clip_path="Assets/Animations/HeavyPunch.anim",
      target_path="",
      type_name="UnityEngine.Transform",
      property_name="m_LocalPosition",
      time=0.458,
      hold_until=0.541,  # Hold for 2 frames at 24 fps
  )
  ```
- Repeat for rotation curves if necessary, or apply hold to the root motion / effector curves.
- Verify `backup_id` is returned so the modification can be rolled back via `restore_animation_clip`.

#### 3. Synchronize camera recoil & verify framing

The camera response must be an impulse triggered at $T_{\text{impact}}$:
- **Inspect cameras:** Call `list_scene_cameras()` to get the active scene camera.
- **Framing preflight:** Call `diagnose_camera_framing(subject_path="Characters/Attacker", camera_name="Main Camera")`.
  Confirm `is_clipped=False` and `is_off_screen=False`.
- **Project critical points:** Call `project_world_points` with the target's head, weapon tip, and impact point
  to verify that camera recoil will not kick key action out of the viewport (coordinates outside $[0, 1]$).
- **Recoil impulse:** Apply a camera kick aligned with or opposite to the attack impulse vector at $T_{\text{impact}}$,
  with an exponential or critically damped decay back to baseline. Never leave residual offsets on the camera transform.

#### 4. Author authoritative animation events & VFX

All impact flashes, hit sparks, sound triggers, and screen flashes must share $T_{\text{impact}}$:
- Call `create_animation_event`:
  ```python
  create_animation_event(
      clip_path="Assets/Animations/HeavyPunch.anim",
      time=0.458,
      function_name="OnHitImpact",
      string_param="HeavyImpact_Flesh",
  )
  ```
- Do not let game logic rely on approximate timer coroutines (`yield return new WaitForSeconds(...)`);
  the `AnimationEvent` guarantees perfect frame-accurate synchronization with the visual pose.

#### 5. Verification loop: Windowed preview

Verify the synchronized action sequence in a focused window around impact:
- Call `preview_animation` covering $[T_{\text{impact}} - 0.4s, T_{\text{impact}} + 0.4s]$:
  ```python
  preview_animation(
      target_object_path="Characters/Attacker",
      clip_path="Assets/Animations/HeavyPunch.anim",
      start_time=0.058,
      end_time=0.858,
      width=480,
      height=270,
      fps=24,
      auto_frame=False,  # Keep fixed camera to evaluate camera recoil
  )
  ```
- **Evaluate results:**
  - `motion_intensity`: Look for high energy leading up to $T_{\text{impact}}$, a sharp plateau near zero
    during hit-stop, and an energy spike upon recovery.
  - Review keyframe captures to verify camera recoil framing and subject visibility.
  - Once validated, render final-quality capture using `preview_animation` or `get_video_mp4` at full resolution.
