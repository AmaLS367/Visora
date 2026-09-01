import math
from typing import Any

from backend.schemas.animation import (
    AnimationBindingCurve,
    DangerousCurveWarning,
    TransformPose,
)


def _check_nan_inf_and_extremes(b: AnimationBindingCurve) -> list[DangerousCurveWarning]:
    """Checks for NaN, Inf, and extreme numeric values in curve keyframes."""
    warnings: list[DangerousCurveWarning] = []
    prop = b.property_name
    path = b.path

    # Check for NaN / Inf
    for val, val_name in [
        (b.min_value, "min_value"),
        (b.max_value, "max_value"),
        (b.start_value, "start_value"),
        (b.end_value, "end_value"),
    ]:
        if val is not None and (math.isnan(val) or math.isinf(val)):
            warnings.append(
                DangerousCurveWarning(
                    risk_level="critical",
                    binding_path=path,
                    property_name=prop,
                    reason=f"Invalid float ({val_name} is NaN/Inf)",
                    description=f"Keyframe data for {path}:{prop} contains non-finite numerical values.",
                    recommendation="Re-export or clean up corrupted keyframes in the animation asset.",
                )
            )

    # Extreme values (> 1000.0 or < -1000.0)
    if (b.max_value is not None and b.max_value > 1000.0) or (b.min_value is not None and b.min_value < -1000.0):
        warnings.append(
            DangerousCurveWarning(
                risk_level="critical",
                binding_path=path,
                property_name=prop,
                reason="Extreme keyframe value",
                description=f"Property {path}:{prop} has extreme values [{b.min_value}, {b.max_value}].",
                recommendation="Verify animation scale and units; check for explosion or corrupted export.",
            )
        )

    return warnings


def _check_scale_curve(b: AnimationBindingCurve) -> list[DangerousCurveWarning]:
    """Checks for negative scale and dynamic bone scale risks."""
    warnings: list[DangerousCurveWarning] = []
    prop = b.property_name
    path = b.path

    if (b.min_value is not None and b.min_value < 0.0) or (b.max_value is not None and b.max_value < 0.0):
        warnings.append(
            DangerousCurveWarning(
                risk_level="critical",
                binding_path=path,
                property_name=prop,
                reason="Negative scale animation",
                description=f"Scale curve on '{path}' contains negative values [{b.min_value}, {b.max_value}], causing inverted geometry and flipped normals.",
                recommendation="Remove negative scale keyframes or invert mesh vertices in modeling software.",
            )
        )
    elif not b.is_constant:
        warnings.append(
            DangerousCurveWarning(
                risk_level="warning",
                binding_path=path,
                property_name=prop,
                reason="Animated bone scale",
                description=f"Bone '{path}' animates dynamic scale ({prop}). Bone scaling frequently causes skinned mesh deformation, volume loss, or non-uniform distortion.",
                recommendation="Ensure bone scale animation is intentional; prefer skeletal rotation or blendshapes.",
            )
        )
    return warnings


def _check_position_curve(b: AnimationBindingCurve) -> list[DangerousCurveWarning]:
    """Checks for non-root position animations and excessive root displacement."""
    warnings: list[DangerousCurveWarning] = []
    prop = b.property_name
    path = b.path
    is_root = path == "" or path.lower() in ("root", "hips", "armature", "bip01")

    if not is_root and not b.is_constant:
        warnings.append(
            DangerousCurveWarning(
                risk_level="warning",
                binding_path=path,
                property_name=prop,
                reason="Local position animation on non-root bone",
                description=f"Bone '{path}' has local position animation ({prop}). In standard humanoid/skeletal rigs, translating child bones breaks joint constraints and causes limb dismemberment.",
                recommendation="Remove local position curves from child bones unless stretchy limbs are intended.",
            )
        )
    elif is_root and b.min_value is not None and b.max_value is not None:
        delta = abs(b.max_value - b.min_value)
        if delta > 50.0:
            warnings.append(
                DangerousCurveWarning(
                    risk_level="warning",
                    binding_path=path,
                    property_name=prop,
                    reason="Large root displacement",
                    description=f"Root position curve ({prop}) travels {delta:.2f} units. This may cause significant character drifting or clipping.",
                    recommendation="Check if Root Motion should be baked into pose or handled by character controller.",
                )
            )
    return warnings


def detect_dangerous_curves(
    bindings: list[AnimationBindingCurve],
    clip_length: float = 0.0,
    has_root_motion: bool = False,
) -> tuple[list[DangerousCurveWarning], dict[str, Any]]:
    """
    Analyzes animation curves and bindings to detect hazardous, unintended, or malformed curves.

    Returns:
        A tuple of (list of DangerousCurveWarning, summary_metrics dictionary).
    """
    warnings: list[DangerousCurveWarning] = []

    position_curves_count = 0
    rotation_curves_count = 0
    scale_curves_count = 0
    constant_curves_count = 0

    for b in bindings:
        prop = b.property_name
        path = b.path
        c_type = b.curve_type

        if c_type == "position" or prop.startswith("m_LocalPosition"):
            position_curves_count += 1
            warnings.extend(_check_position_curve(b))
        elif c_type == "rotation" or prop.startswith("m_LocalRotation") or prop.startswith("localEulerAngles"):
            rotation_curves_count += 1
        elif c_type == "scale" or prop.startswith("m_LocalScale"):
            scale_curves_count += 1
            warnings.extend(_check_scale_curve(b))

        if b.is_constant:
            constant_curves_count += 1
            if b.keyframe_count > 1:
                warnings.append(
                    DangerousCurveWarning(
                        risk_level="info",
                        binding_path=path,
                        property_name=prop,
                        reason="Static flat curve",
                        description=f"Curve on '{path}' ({prop}) has identical values across all {b.keyframe_count} keyframes.",
                        recommendation="Remove redundant flat curves to reduce animation clip size and memory footprint.",
                    )
                )

        warnings.extend(_check_nan_inf_and_extremes(b))

    critical_count = sum(1 for w in warnings if w.risk_level == "critical")

    summary_metrics = {
        "total_curves": len(bindings),
        "position_curves_count": position_curves_count,
        "rotation_curves_count": rotation_curves_count,
        "scale_curves_count": scale_curves_count,
        "constant_curves_count": constant_curves_count,
        "dangerous_curves_count": len(warnings),
        "critical_warnings_count": critical_count,
    }

    return warnings, summary_metrics


def analyze_sampled_pose(
    sampled_transforms: dict[str, TransformPose],
) -> tuple[list[str], list[str]]:
    """
    Inspects sampled transform poses to detect anomalies, inverted scales, or out-of-bounds positions.

    Returns:
        A tuple of (anomalies list, warnings list).
    """
    anomalies: list[str] = []
    warnings: list[str] = []

    for path, pose in sampled_transforms.items():
        name = pose.name or path or "Root"

        # Check for NaN / Inf
        vectors_to_check = [
            ("local_position", pose.local_position),
            ("local_rotation_euler", pose.local_rotation_euler),
            ("local_scale", pose.local_scale),
        ]
        if pose.world_position:
            vectors_to_check.append(("world_position", pose.world_position))

        has_nan = False
        for vec_name, vec in vectors_to_check:
            if any(math.isnan(v) or math.isinf(v) for v in vec):
                anomalies.append(f"NaN or Infinite coordinates in {vec_name} on transform '{name}' ({path}).")
                has_nan = True
                break

        if has_nan:
            continue

        # Check negative local scale
        if any(s < 0.0 for s in pose.local_scale):
            anomalies.append(f"Negative local scale {pose.local_scale} detected on transform '{name}' ({path}).")

        # Check extreme scale
        if any(s > 20.0 or (0.0 < s < 0.001) for s in pose.local_scale):
            warnings.append(f"Abnormal local scale {pose.local_scale} detected on transform '{name}' ({path}).")

        # Check extreme world position / ground clipping
        if pose.world_position:
            y = pose.world_position[1]
            if y < -50.0:
                warnings.append(
                    f"Transform '{name}' world position Y={y:.2f} is significantly below ground plane level."
                )

    return anomalies, warnings
