import math
from typing import Any

from backend.schemas.mesh import (
    BoneBindingInfo,
    BoundsInfo,
    DeformationInfo,
    DiagnosticIssue,
    MaterialSlotInfo,
    SubMeshInfo,
)


def _is_invalid_float(v: float | None) -> bool:
    """Returns True if the float is None, NaN, or infinite."""
    if v is None:
        return True
    return math.isnan(v) or math.isinf(v)


def analyze_bounds(
    local_center: list[float] | None,
    local_size: list[float] | None,
    world_center: list[float] | None,
    world_size: list[float] | None,
    update_when_offscreen: bool = False,
) -> tuple[BoundsInfo, list[DiagnosticIssue]]:
    """
    Pure analysis of local and world bounding boxes.
    Detects zero-volume bounds, NaN/Inf values, extreme sizes, and culling misconfigurations.
    """
    issues: list[DiagnosticIssue] = []

    lc = list(local_center) if local_center and len(local_center) == 3 else [0.0, 0.0, 0.0]
    ls = list(local_size) if local_size and len(local_size) == 3 else [0.0, 0.0, 0.0]
    wc = list(world_center) if world_center and len(world_center) == 3 else [0.0, 0.0, 0.0]
    ws = list(world_size) if world_size and len(world_size) == 3 else [0.0, 0.0, 0.0]

    # Check for NaN / Inf
    has_nan_inf = any(_is_invalid_float(x) for x in lc + ls + wc + ws)
    if has_nan_inf:
        issues.append(
            DiagnosticIssue(
                category="bounds",
                severity="error",
                message="Bounding box contains NaN or Infinity values, causing culling failure or invisible mesh.",
                details={"local_center": lc, "local_size": ls, "world_center": wc, "world_size": ws},
            )
        )

    # Check for zero volume
    is_zero_volume = any(s <= 1e-6 for s in ls) or any(s <= 1e-6 for s in ws)
    if is_zero_volume and not has_nan_inf:
        issues.append(
            DiagnosticIssue(
                category="bounds",
                severity="error",
                message="Bounding box has zero or near-zero volume, which will cause Unity camera culling to clip the mesh unexpectedly.",
                details={"local_size": ls, "world_size": ws},
            )
        )

    # Check for abnormal / giant bounds (> 1000m)
    is_giant = any(abs(s) > 1000.0 for s in ls + ws) or any(abs(c) > 10000.0 for s in [lc, wc] for c in s)
    if is_giant and not has_nan_inf:
        issues.append(
            DiagnosticIssue(
                category="bounds",
                severity="warning",
                message="Bounding box size is unusually large (>1000 units), potentially indicating invalid vertex positions or incorrect bone transforms.",
                details={"local_size": ls, "world_size": ws},
            )
        )

    is_abnormal = has_nan_inf or is_giant

    bounds_info = BoundsInfo(
        local_center=lc,
        local_size=ls,
        world_center=wc,
        world_size=ws,
        is_zero_volume=is_zero_volume,
        is_abnormal=is_abnormal,
        update_when_offscreen=update_when_offscreen,
    )

    return bounds_info, issues


def analyze_bones(
    bones_data: list[dict[str, Any]],
    has_root_bone: bool,
    root_bone_path: str | None,
    bind_poses_count: int,
    vertex_count: int,
) -> tuple[list[BoneBindingInfo], list[DiagnosticIssue]]:
    """
    Pure analysis of SkinnedMeshRenderer bone attachments.
    Detects unassigned (null) bone slots, missing root bone, and bindpose count mismatches.
    """
    issues: list[DiagnosticIssue] = []
    bone_bindings: list[BoneBindingInfo] = []

    null_indices: list[int] = []

    for i, b in enumerate(bones_data):
        is_null = bool(b.get("isNull", False))
        name = b.get("name")
        path = b.get("path")

        if is_null:
            null_indices.append(i)

        has_bindpose = i < bind_poses_count if bind_poses_count > 0 else True

        bone_bindings.append(
            BoneBindingInfo(
                bone_index=i,
                bone_name=name,
                bone_path=path,
                is_null=is_null,
                has_bindpose=has_bindpose,
            )
        )

    if null_indices:
        issues.append(
            DiagnosticIssue(
                category="geometry_skinning",
                severity="error",
                message=f"SkinnedMeshRenderer contains {len(null_indices)} unassigned (null) bone slots at indices {null_indices}. Vertices weighted to these bones will collapse to the world origin.",
                details={"null_bone_indices": null_indices},
            )
        )

    if not has_root_bone and vertex_count > 0:
        issues.append(
            DiagnosticIssue(
                category="geometry_skinning",
                severity="warning",
                message="SkinnedMeshRenderer does not have a rootBone assigned. Bounding box calculation and motion culling may be inaccurate.",
                details={"root_bone_path": root_bone_path},
            )
        )

    if bind_poses_count > 0 and len(bones_data) != bind_poses_count:
        issues.append(
            DiagnosticIssue(
                category="geometry_skinning",
                severity="warning",
                message=f"Mismatch between bones array count ({len(bones_data)}) and sharedMesh.bindposes count ({bind_poses_count}). This can lead to incorrect vertex transformation.",
                details={"bone_count": len(bones_data), "bind_poses_count": bind_poses_count},
            )
        )

    return bone_bindings, issues


def analyze_materials_and_submeshes(
    materials_data: list[dict[str, Any]],
    submeshes_data: list[dict[str, Any]],
) -> tuple[list[MaterialSlotInfo], list[SubMeshInfo], list[DiagnosticIssue]]:
    """
    Pure analysis of material slots and submeshes.
    Detects material count mismatches, missing materials, error shaders (pink shader), and missing textures.
    """
    issues: list[DiagnosticIssue] = []
    materials: list[MaterialSlotInfo] = []
    submeshes: list[SubMeshInfo] = []

    mat_count = len(materials_data)
    submesh_count = len(submeshes_data)

    for i, m in enumerate(materials_data):
        is_missing = bool(m.get("isMissing", False))
        mat_name = m.get("name")
        shader_name = m.get("shaderName")
        is_error_shader = bool(m.get("isErrorShader", False))
        main_tex = m.get("mainTextureName")
        has_main_tex = bool(m.get("hasMainTexture", False))

        if is_missing:
            issues.append(
                DiagnosticIssue(
                    category="texture_material",
                    severity="error",
                    message=f"Material slot #{i} is unassigned (missing material). Submesh will render invisible or pink.",
                    details={"slot_index": i},
                )
            )
        elif is_error_shader:
            issues.append(
                DiagnosticIssue(
                    category="texture_material",
                    severity="error",
                    message=f"Material slot #{i} ('{mat_name}') uses an unsupported or broken shader ('{shader_name}'), causing pink/magenta error rendering.",
                    details={"slot_index": i, "material_name": mat_name, "shader_name": shader_name},
                )
            )

        materials.append(
            MaterialSlotInfo(
                slot_index=i,
                material_name=mat_name,
                shader_name=shader_name,
                is_missing=is_missing,
                is_error_shader=is_error_shader,
                main_texture_name=main_tex,
                has_main_texture=has_main_tex,
            )
        )

    for j, sm in enumerate(submeshes_data):
        idx_count = int(sm.get("indexCount", 0))
        top = str(sm.get("topology", "Triangles"))
        v_count = idx_count // 3 if top == "Triangles" else idx_count

        has_match = j < mat_count and not materials[j].is_missing

        if j >= mat_count:
            issues.append(
                DiagnosticIssue(
                    category="texture_material",
                    severity="error",
                    message=f"Submesh #{j} has no corresponding material slot (mesh has {submesh_count} submeshes but renderer only has {mat_count} materials).",
                    details={"submesh_index": j, "material_count": mat_count},
                )
            )

        submeshes.append(
            SubMeshInfo(
                submesh_index=j,
                vertex_count=v_count,
                triangle_count=idx_count // 3 if top == "Triangles" else 0,
                has_matching_material=has_match,
                topology=top,
            )
        )

    if mat_count > submesh_count > 0:
        issues.append(
            DiagnosticIssue(
                category="texture_material",
                severity="info",
                message=f"Renderer has {mat_count} material slots, but mesh only has {submesh_count} submeshes. Unused material slots add unnecessary draw calls.",
                details={"material_count": mat_count, "submesh_count": submesh_count},
            )
        )

    return materials, submeshes, issues


def analyze_deformation(
    blendshapes_data: list[dict[str, Any]],
    root_bone_scale: list[float] | None,
    root_bone_path: str | None,
    bones_data: list[dict[str, Any]],
) -> tuple[DeformationInfo, list[DiagnosticIssue]]:
    """
    Pure analysis of mesh deformation integrity, blendshapes, and transform scales.
    Detects zero/negative bone scales and extreme blendshape values.
    """
    issues: list[DiagnosticIssue] = []
    active_bs: list[dict[str, Any]] = []

    for bs in blendshapes_data:
        name = str(bs.get("name", ""))
        weight = float(bs.get("weight", 0.0))
        if abs(weight) > 1e-4:
            active_bs.append({"name": name, "weight": weight})

        if weight < -10.0 or weight > 150.0:
            issues.append(
                DiagnosticIssue(
                    category="deformation",
                    severity="warning",
                    message=f"Blendshape '{name}' has an unusual weight of {weight:.1f} (typical range is 0 to 100), which may cause severe mesh distortion.",
                    details={"blendshape_name": name, "weight": weight},
                )
            )

    has_bad_scale = False
    if root_bone_scale and len(root_bone_scale) == 3:
        if any(abs(s) <= 1e-6 or s < 0 for s in root_bone_scale):
            has_bad_scale = True
            issues.append(
                DiagnosticIssue(
                    category="geometry_skinning",
                    severity="error",
                    message=f"Root bone scale {root_bone_scale} contains zero or negative dimensions, causing mesh deformation to flatten or invert.",
                    details={"root_bone_scale": root_bone_scale, "root_bone_path": root_bone_path},
                )
            )

    for b in bones_data:
        if not b.get("isNull", False):
            scale = b.get("lossyScale")
            if scale and len(scale) == 3 and any(abs(s) <= 1e-6 or s < 0 for s in scale):
                has_bad_scale = True
                issues.append(
                    DiagnosticIssue(
                        category="geometry_skinning",
                        severity="warning",
                        message=f"Bone '{b.get('name')}' has degenerate or negative scale {scale}.",
                        details={"bone_name": b.get("name"), "bone_path": b.get("path"), "lossy_scale": scale},
                    )
                )

    deform_info = DeformationInfo(
        has_blendshapes=len(blendshapes_data) > 0,
        blendshape_count=len(blendshapes_data),
        active_blendshapes=active_bs,
        root_bone_path=root_bone_path,
        root_bone_scale=root_bone_scale,
        has_non_uniform_or_zero_scale=has_bad_scale,
    )

    return deform_info, issues


def classify_diagnostics(
    issues: list[DiagnosticIssue],
) -> tuple[str, bool, bool, bool, bool]:
    """
    Classifies the primary root cause category and computes summary boolean flags.
    Distinguishes geometry/skinning bugs from texture/material bugs, bounds issues, and deformation bugs.
    """
    has_bounds_issue = any(i.category == "bounds" and i.severity in ("error", "warning") for i in issues)
    has_broken_bones = any(
        i.category == "geometry_skinning" and "bone" in i.message.lower() and i.severity in ("error", "warning")
        for i in issues
    )
    has_material_mismatch = any(i.category == "texture_material" and i.severity == "error" for i in issues)
    has_deformation_issue = any(
        i.category in ("deformation", "geometry_skinning") and i.severity in ("error", "warning") for i in issues
    )

    if not issues:
        return "none", False, False, False, False

    # Score categories by error (weight 3) and warning (weight 1)
    category_scores: dict[str, int] = {
        "geometry_skinning": 0,
        "texture_material": 0,
        "bounds": 0,
        "deformation": 0,
    }

    for iss in issues:
        weight = 3 if iss.severity == "error" else 1
        cat = iss.category if iss.category in category_scores else "geometry_skinning"
        category_scores[cat] += weight

    best_category = max(category_scores, key=lambda k: category_scores[k])
    if category_scores[best_category] == 0:
        primary_category = "none"
    else:
        primary_category = best_category

    return (
        primary_category,
        has_bounds_issue,
        has_broken_bones,
        has_material_mismatch,
        has_deformation_issue,
    )
