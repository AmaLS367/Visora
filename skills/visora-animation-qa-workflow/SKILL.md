---
name: visora-animation-qa-workflow
description: Use before finalizing or committing character animations. Prescribes an automated quality assurance pass covering curve discontinuity scans, jerk and snapping analysis, foot sliding verification, and before/after regression checks.
---

## Visora animation QA workflow

Visora exposes high-level MCP tools for rigorous mathematical animation inspection:
`detect_curve_discontinuities`, `analyze_joint_motion`, `analyze_contact_constraints`,
`compare_animation_previews`, and `preview_animation`.

Always run this automated QA loop before declaring an animation task complete.

---

### Golden rules

1. **Never commit an animation without running temporal QA.**
   Visual inspection alone cannot catch high-frequency jerk spikes ($> 120\text{m/s}^3$) or
   subtle foot sliding ($> 0.03\text{m}$). Always quantify motion mathematically.
2. **Treat quaternion sign flips as critical defects.**
   If `detect_curve_discontinuities` finds antipodal flips ($q_1 \cdot q_2 < 0$), they must be
   fixed immediately with `auto_fix=True`. Leaving them in curves causes 360° rotational pops.
3. **Never accept regressions.**
   When modifying an animation to fix a pose or timing issue, always compare the result
   against the baseline with `compare_animation_previews`. Ensure sliding and jerk did not worsen.
4. **Never infer smoothness from a static screenshot.**
   Evaluate motion continuously across time via `preview_animation` in Edit Mode.

---

### Step-by-step QA verification sequence

#### 1. Scan curves for discontinuities & flips

Scan all curves for quaternion flips and tangent singularities:
```python
detect_curve_discontinuities(clip_path="Assets/Animations/Hero_Attack.anim", auto_fix=True)
```
If `discontinuities_count > 0` and `fix_applied == True`, confirm `backup_id` is recorded.

#### 2. Run high-order derivative motion & jerk analysis

Detect violent acceleration changes, knee popping, and velocity snaps:
```python
analyze_joint_motion(
    clip_path="Assets/Animations/Hero_Attack.anim",
    target_object_path="Characters/Hero",
    sample_fps=60,
    jerk_threshold=120.0,
    angular_jerk_threshold=4000.0,
)
```
Inspect:
- `overall_smoothness_score`: aim for $\ge 0.85$.
- `anomalies`: examine flagged timestamps. If knee or elbow jerk spikes occur near impact,
  adjust tangents or check limb reachability.

#### 3. Verify contact dynamics and foot sliding

Ensure feet or effectors do not slide across the ground during stance phases:
```python
analyze_contact_constraints(target_object_path="Characters/Hero", clip_path="Assets/Animations/Hero_Attack.anim")
```
Verify `total_slide_distance <= 0.05` meters and `max_ground_penetration <= 0.02` meters.

#### 4. Compare with baseline to verify improvement

Compare the edited animation with the pre-edit baseline:
```python
compare_animation_previews(
    baseline_preview_id="preview-run-1",
    comparison_preview_id="preview-run-2",
    baseline_slide_distance=0.18,
    comparison_slide_distance=0.02,
    baseline_peak_jerk=240.0,
    comparison_peak_jerk=85.0,
)
```
Confirm `sliding_reduced_percent > 0`, `jerk_reduced_percent > 0`, and no regression warnings exist.
