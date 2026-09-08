---
name: visora-rig-retarget-workflow
description: Use when importing, inspecting, configuring, or retargeting character rigs, Humanoid Avatars, and motion capture (mocap) AnimationClips in Unity. Prescribes rigorous Humanoid preflight, Avatar blocker diagnosis, mocap retarget verification, contact IK baking, and explicit fallback paths for Generic/non-Humanoid rigs.
---

## Visora rig and retarget workflow

Visora exposes tools for inspecting skeletons, configuring Humanoid Avatars, verifying retargeted motion,
and resolving contact constraints:
`inspect_imported_asset`, `skeleton_mapper`, `find_bones`, `validate_humanoid_avatar`,
`configure_humanoid_avatar`, `preview_humanoid_retarget`, `inspect_animation_clip`,
`analyze_contact_constraints`, and `bake_contact_constraints`.

This workflow guides agents through character setup and mocap animation retargeting without broken
joints, stretched meshes, or corrupt FBX imports.

---

### Core principles

1. **Never infer retargeting success from a static screenshot.**
   An imported character might look upright in a static screenshot, but the moment animation plays,
   shoulders collapse, knees bend backward, or the mesh stretches infinitely. Always verify retargeting
   across time using `preview_humanoid_retarget` or `preview_animation`.
2. **Preflight Humanoid eligibility before applying mocap.**
   Do not assume a humanoid-looking 3D model has a valid Humanoid Avatar. Always run
   `validate_humanoid_avatar` first to catch missing required bones, non-T-pose geometry, or non-bipedal
   hierarchies before attempting retargeting.
3. **Explicit fallback for Generic / non-Humanoid rigs.**
   If a model cannot satisfy Unity's Humanoid requirements (e.g. quadrupeds, mechanical robots, vehicles,
   monsters, or skeletons missing vital hip/spine joints), **never force Humanoid import mode**.
   Use the Generic rig fallback path described below.
4. **Report concrete bridge and Unity errors.**
   When Avatar validation or configuration returns blockers or errors, report the exact bone names and
   blocker messages rather than a vague "retargeting failed".

---

### Step-by-step rig & retarget sequence

#### 1. Inspect imported asset & skeleton hierarchy

When an FBX or model is imported into `Assets/`:
- Call `inspect_imported_asset(asset_path="Assets/Models/Character.fbx")`.
  Confirm `asset_type` is valid, `submesh_count > 0`, and materials are mapped.
- Call `skeleton_mapper(root_transform_path="Characters/Character")` or `find_bones` to inspect the joint
  hierarchy. Verify standard anatomical bones (Hips, Spine, Head, Shoulders, Arms, Legs) are present.

#### 2. Validate Humanoid Avatar eligibility

Check whether Unity can construct a Humanoid Avatar for the asset or scene instance:
- Call `validate_humanoid_avatar`:
  ```python
  validate_humanoid_avatar(asset_path="Assets/Models/Character.fbx")
  ```
- **Inspect the result:**
  - `is_valid_humanoid`: `True` indicates the model has all 15 required Humanoid bones and valid posture.
  - `missing_required_bones`: Lists any missing critical bones (e.g. `Hips`, `Spine`, `Head`, `LeftUpperArm`).
  - `posture`: Check `is_tpose` and `warnings`. If arms are angled downwards (e.g. A-pose at 45°),
    posture adjustment may be needed during avatar configuration.
  - `blockers`: Review each `AvatarBlocker` for severity and suggested fixes.

#### 3. Configure Humanoid Avatar (when eligible)

If `validate_humanoid_avatar` identifies fixable bone naming mismatches or unassigned optional bones:
- Call `configure_humanoid_avatar`:
  ```python
  configure_humanoid_avatar(
      asset_path="Assets/Models/Character.fbx",
      bone_mapping_overrides={
          "Chest": "Bip01_Spine1",
          "LeftShoulder": "Bip01_L_Clavicle",
          "RightShoulder": "Bip01_R_Clavicle",
      },
  )
  ```
- Confirm `avatar_created=True` and `avatar_valid=True`. If blockers remain, inspect them before proceeding.

#### 4. Preview mocap retargeting across time

Once the character has a valid Humanoid Avatar, test retargeting with the target mocap clip:
- Call `preview_humanoid_retarget`:
  ```python
  preview_humanoid_retarget(
      target_object_path="Characters/Character",
      clip_path="Assets/Mocap/Walk.anim",
      width=480,
      height=270,
      fps=24,
      auto_frame=True,
  )
  ```
- **Inspect retargeting metrics:**
  - `is_compatible`: Must be `True`. If `False`, examine `issues` (e.g. clip is Generic Transform-based,
    not a Humanoid muscle clip).
  - `height_ratio`: Indicates character proportion scaling relative to the source clip.
  - `issues` & `warnings`: Look for joint over-rotation or limb stretching flags.
  - Review generated key frames and motion video to visually verify limb arcs and balance.

#### 5. Contact analysis & foot sliding correction

Retargeting clips between characters of differing heights and leg lengths frequently introduces foot sliding
or ground penetration:
- Call `analyze_contact_constraints(target_object_path="Characters/Character", clip_path="Assets/Mocap/Walk.anim")`.
- If `total_slide_distance` is significant or `anomalies` reports foot sliding/penetration:
  ```python
  bake_contact_constraints(
      clip_path="Assets/Mocap/Walk.anim",
      target_object_path="Characters/Character",
      fix_foot_sliding=True,
      fix_penetration=True,
  )
  ```
- A backup is saved in `Assets/VisoraBackups/` before baking. If results are unnatural, restore with `restore_animation_clip`.

---

### Generic / No-Avatar fallback path

If `validate_humanoid_avatar` reports fatal blockers that cannot be resolved (such as quadrupeds,
creatures, mechanical machinery, or non-bipedal skeletons):

1. **Never force Humanoid mode:**
   Setting `ModelImporterAnimationType.Human` on an incompatible rig causes Unity's Avatar builder to fail,
   leaving the asset with a broken or null Avatar.
2. **Keep the rig as Generic:**
   Configure or leave the model as `ModelImporterAnimationType.Generic`.
3. **Use Transform-based clips matching the skeleton:**
   Call `inspect_animation_clip(clip_path=...)` to inspect curve bindings. Ensure curves target the exact
   relative transform paths of the Generic skeleton (e.g. `Root/Hips/Tail_01`).
4. **Use IK or procedural solvers for motion adjustments:**
   Instead of relying on Humanoid muscle retargeting, adjust Generic animations using keyframe editing
   (`set_animation_keyframe`, `move_animation_keyframe`) or Two-Bone IK constraints.
