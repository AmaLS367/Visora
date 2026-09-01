import difflib
import math
import re
from typing import Any

from backend.schemas.animation import (
    AnimationBindingCurve,
    BoneMatch,
    BoneNode,
    DangerousCurveWarning,
    DuplicateBoneGroup,
    HelperBoneWarning,
    MmdBoneChain,
    TransformPose,
)

HELPER_BONE_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bhelper\b"), "matches helper naming pattern 'helper'"),
    (re.compile(r"(?i)\bdummy\b"), "matches helper naming pattern 'dummy'"),
    (re.compile(r"(?i)\btwist\b"), "matches helper naming pattern 'twist'"),
    (re.compile(r"(?i)\badjust\b"), "matches helper naming pattern 'adjust'"),
    (re.compile(r"(?i)\baux\b"), "matches helper naming pattern 'aux'"),
    (re.compile(r"(?i)\broll\b"), "matches helper naming pattern 'roll'"),
    (re.compile(r"(?i)_end$"), "matches helper naming pattern '_end' suffix"),
    (re.compile(r"(?i)^ik[_ ]"), "matches helper naming pattern 'ik_' prefix"),
]

MMD_D_BONE_SUFFIX_RE = re.compile(r"(?i)^(?P<base>.+)_d$")

HUMANOID_MATCH_THRESHOLD = 0.6


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


def detect_duplicate_bones(bones: list[BoneNode]) -> list[DuplicateBoneGroup]:
    """
    Groups bones by their exact name and reports every name shared by two or more bones.

    Returns:
        A list of DuplicateBoneGroup, one per duplicated name.
    """
    by_name: dict[str, list[str]] = {}
    for b in bones:
        by_name.setdefault(b.name, []).append(b.path)

    return [DuplicateBoneGroup(name=name, paths=paths) for name, paths in sorted(by_name.items()) if len(paths) > 1]


def detect_helper_bones(bones: list[BoneNode]) -> list[HelperBoneWarning]:
    """
    Flags bones whose name matches a common helper/dummy/twist/IK naming convention.

    Returns:
        A list of HelperBoneWarning, one per flagged bone.
    """
    warnings: list[HelperBoneWarning] = []
    for b in bones:
        for pattern, reason in HELPER_BONE_NAME_PATTERNS:
            if pattern.search(b.name):
                warnings.append(HelperBoneWarning(path=b.path, name=b.name, reason=reason))
                break
    return warnings


def detect_mmd_bone_chains(bones: list[BoneNode]) -> list[MmdBoneChain]:
    """
    Detects MMD-style primary/physics bone chains, where a physics ("dynamics") bone is
    named as the primary bone's base name with a '_D' (or '_d') suffix.

    Returns:
        A list of MmdBoneChain, one per matched primary/D-bone pair.
    """
    path_by_name: dict[str, str] = {b.name: b.path for b in bones}
    chains: list[MmdBoneChain] = []

    for b in bones:
        match = MMD_D_BONE_SUFFIX_RE.match(b.name)
        if not match:
            continue
        base_name = match.group("base")
        primary_path = path_by_name.get(base_name)
        if primary_path is not None:
            chains.append(MmdBoneChain(base_name=base_name, primary_path=primary_path, d_bone_path=b.path))

    return chains


def match_bones_fuzzy(
    query: str,
    bones: list[BoneNode],
    limit: int = 10,
    exact_only: bool = False,
) -> list[BoneMatch]:
    """
    Finds bones matching a query name, exact (case-insensitive) matches first, followed by
    fuzzy matches ranked by similarity ratio.

    Returns:
        A list of BoneMatch, best matches first, capped at `limit`.
    """
    if limit <= 0 or not bones:
        return []

    query_lower = query.lower()
    matches: list[BoneMatch] = []
    matched_paths: set[str] = set()

    for b in bones:
        if b.name.lower() == query_lower:
            matches.append(BoneMatch(path=b.path, name=b.name, match_type="exact", score=1.0))
            matched_paths.add(b.path)

    if not exact_only and len(matches) < limit:
        remaining = [b for b in bones if b.path not in matched_paths]
        scored = sorted(
            ((difflib.SequenceMatcher(a=query_lower, b=b.name.lower()).ratio(), b) for b in remaining),
            key=lambda pair: pair[0],
            reverse=True,
        )
        for score, b in scored:
            if len(matches) >= limit:
                break
            if score <= 0.0:
                continue
            matches.append(BoneMatch(path=b.path, name=b.name, match_type="fuzzy", score=round(score, 4)))

    return matches[:limit]


def map_humanoid_bones(
    bones: list[BoneNode],
    required_names: list[str],
    avatar_human_bones: list[tuple[str, str]] | None,
) -> tuple[bool, str, dict[str, str], list[str]]:
    """
    Maps standard humanoid bone names to transform paths, preferring an authoritative Unity
    Avatar mapping when available and falling back to fuzzy name matching otherwise.

    Returns:
        A tuple of (is_valid, mapping_source, mappings, missing_bones).
    """
    path_by_name: dict[str, str] = {b.name: b.path for b in bones}

    if avatar_human_bones:
        mappings = {
            human_name: path_by_name[bone_name]
            for human_name, bone_name in avatar_human_bones
            if bone_name in path_by_name
        }
        missing_bones = [name for name in required_names if name not in mappings]
        return len(missing_bones) == 0, "avatar", mappings, missing_bones

    mappings = {}
    missing_bones = []
    for required_name in required_names:
        candidates = match_bones_fuzzy(required_name, bones, limit=1)
        if candidates and candidates[0].score >= HUMANOID_MATCH_THRESHOLD:
            mappings[required_name] = candidates[0].path
        else:
            missing_bones.append(required_name)

    return len(missing_bones) == 0, "heuristic", mappings, missing_bones
