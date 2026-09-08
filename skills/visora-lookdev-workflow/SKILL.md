---
name: visora-lookdev-workflow
description: Use before evaluating or adjusting environment lighting, materials, shaders, and camera composition. Prescribes verifying scene illumination contrast, material albedo ranges, exposure balance, and silhouette readability.
---

## Visora lookdev workflow

Visora exposes high-level MCP tools for environment and visual inspection:
`capture_camera_screenshot`, `diagnose_camera_framing`, `diagnose_mesh_issues`,
`inspect_asset`, and `project_world_points`.

Character motion requires strong silhouette readability and lighting contrast. Washed-out,
flat, or unlit environments compromise animation readability. Always verify lookdev
before evaluating cinematic shots.

---

### Golden rules

1. **Every subject requires clear silhouette contrast.**
   The character's outline must separate clearly from background geometry and skies.
   Use rim lighting or exposure separation to maintain readability.
2. **Never leave scenes in unlit or default ambient-only illumination.**
   A proper three-point lighting scheme (key light, fill light, rim light) or a calibrated
   skybox ensures depth, shadow casting, and form definition.
3. **Verify material slots and shader assignment.**
   Ensure characters do not render with magenta (missing shader) or default grey materials
   via `diagnose_mesh_issues`.
4. **Never evaluate lighting solely from scene view.**
   Always inspect through the active game camera using `capture_camera_screenshot` to
   evaluate post-processing, tone-mapping, and exposure accurately.

---

### Step-by-step lookdev sequence

#### 1. Inspect camera framing & subject bounds

Diagnose subject positioning and visibility:
```python
diagnose_camera_framing(subject_path="Characters/Hero", camera_name="Main Camera")
```
Confirm that the subject occupies a balanced portion of the frame without clipping
camera frustum planes.

#### 2. Check mesh materials & vertex attributes

Verify that character meshes have valid materials, skin weights, and UVs:
```python
diagnose_mesh_issues(target_name="Hero_Mesh")
```
Ensure `material_count > 0` and no missing shader issues are reported.

#### 3. Capture camera render & evaluate exposure

Render an authoritative screenshot through the game camera:
```python
capture_camera_screenshot(camera_name="Main Camera", width=1920, height=1080)
```
Evaluate:
- Silhouette clarity against environment backdrop.
- Shadow definition on the ground plane (grounds the character).
- Highlights and rim illumination separating limbs from the torso.
