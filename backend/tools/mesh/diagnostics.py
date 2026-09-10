from typing import Any

import backend.tools.mesh as mesh_pkg
from backend.app import mcp
from backend.config import get_settings
from backend.schemas.mesh import SkinnedMeshDiagnosticsResult
from backend.tools.errors import bridge_error
from backend.tools.mesh.analysis import (
    analyze_bones,
    analyze_bounds,
    analyze_deformation,
    analyze_materials_and_submeshes,
    classify_diagnostics,
)
from backend.tools.mesh.scripts import _skinned_mesh_diagnostics_code


@mcp.tool()
async def skinned_mesh_diagnostics(
    mesh_renderer_path: str,
    max_bone_bindings: int | None = None,
) -> SkinnedMeshDiagnosticsResult:
    """
    Performs runtime diagnostics on a SkinnedMeshRenderer component, verifying mesh deformation,
    bounding box validity, bone bindings, material/submesh alignment, and distinguishing
    geometry/skinning bugs from texture/material bugs. Truncates full bone_bindings list to protect
    context window; detected problems remain highlighted in 'issues'.

    Args:
        mesh_renderer_path: Hierarchical path in the active scene to the GameObject holding the SkinnedMeshRenderer.
        max_bone_bindings: Optional maximum number of bone bindings to return (defaults to DIAGNOSTIC_MAX_BONE_BINDINGS).

    Returns:
        A typed SkinnedMeshDiagnosticsResult detailing mesh stats, bounds, bone attachments,
        material assignments, detected issues, and classified primary bug categories.
    """
    try:
        code = _skinned_mesh_diagnostics_code(mesh_renderer_path)
        resp = await mesh_pkg.bridge.execute_capability(code)

        result_data = resp.get("result")
        if not isinstance(result_data, dict):
            result_data = resp

        if not result_data.get("success", False):
            error_msg = str(result_data.get("error", "Unknown Unity error during skinned mesh inspection"))
            return SkinnedMeshDiagnosticsResult(
                success=False,
                error=error_msg,
                mesh_renderer_path=mesh_renderer_path,
            )

        if not result_data.get("hasSharedMesh", False):
            return SkinnedMeshDiagnosticsResult(
                success=True,
                mesh_renderer_path=mesh_renderer_path,
                mesh_name=None,
                vertex_count=0,
                submesh_count=0,
                material_count=0,
                bone_count=0,
                warnings=["No sharedMesh is assigned to the SkinnedMeshRenderer component."],
            )

        raw_bones: list[dict[str, Any]] = result_data.get("bones", [])
        raw_mats: list[dict[str, Any]] = result_data.get("materials", [])
        raw_submeshes: list[dict[str, Any]] = result_data.get("submeshes", [])
        raw_blendshapes: list[dict[str, Any]] = result_data.get("blendshapes", [])

        vertex_count = int(result_data.get("vertexCount", 0))
        submesh_count = int(result_data.get("subMeshCount", 0))
        bind_poses_count = int(result_data.get("bindPosesCount", 0))
        has_root_bone = bool(result_data.get("hasRootBone", False))
        root_bone_path = result_data.get("rootBonePath")
        root_bone_scale = result_data.get("rootBoneScale")
        update_offscreen = bool(result_data.get("updateWhenOffscreen", False))

        local_center = result_data.get("localCenter")
        local_size = result_data.get("localSize")
        world_center = result_data.get("worldCenter")
        world_size = result_data.get("worldSize")

        bounds_info, bounds_issues = analyze_bounds(
            local_center=local_center,
            local_size=local_size,
            world_center=world_center,
            world_size=world_size,
            update_when_offscreen=update_offscreen,
        )

        bone_bindings, bone_issues = analyze_bones(
            bones_data=raw_bones,
            has_root_bone=has_root_bone,
            root_bone_path=root_bone_path,
            bind_poses_count=bind_poses_count,
            vertex_count=vertex_count,
        )

        materials, submeshes, mat_issues = analyze_materials_and_submeshes(
            materials_data=raw_mats,
            submeshes_data=raw_submeshes,
        )

        deformation, deform_issues = analyze_deformation(
            blendshapes_data=raw_blendshapes,
            root_bone_scale=root_bone_scale,
            root_bone_path=root_bone_path,
            bones_data=raw_bones,
        )

        all_issues = bounds_issues + bone_issues + mat_issues + deform_issues

        (
            primary_category,
            has_bounds_issue,
            has_broken_bones,
            has_material_mismatch,
            has_deformation_issue,
        ) = classify_diagnostics(all_issues)

        warnings = [i.message for i in all_issues if i.severity in ("warning", "info")]

        is_sub_mesh_valid = not has_material_mismatch and all(sm.has_matching_material for sm in submeshes)

        settings = get_settings()
        limit = max_bone_bindings if max_bone_bindings is not None else settings.diagnostic_max_bone_bindings
        if limit is not None and len(bone_bindings) > limit:
            broken_slots = [b for b in bone_bindings if b.is_null]
            normal_slots = [b for b in bone_bindings if not b.is_null]
            truncated_bindings = (broken_slots + normal_slots)[:limit]
            warnings.append(
                f"Showing {len(truncated_bindings)} of {len(bone_bindings)} bone bindings. "
                "All detected bone issues are detailed in 'issues'."
            )
        else:
            truncated_bindings = bone_bindings

        return SkinnedMeshDiagnosticsResult(
            success=True,
            mesh_renderer_path=mesh_renderer_path,
            mesh_name=result_data.get("meshName"),
            vertex_count=vertex_count,
            submesh_count=submesh_count,
            material_count=len(materials),
            bone_count=len(bone_bindings),
            bounds_center=bounds_info.local_center,
            bounds_size=bounds_info.local_size,
            is_sub_mesh_valid=is_sub_mesh_valid,
            has_bounds_issue=has_bounds_issue,
            has_broken_bones=has_broken_bones,
            has_material_mismatch=has_material_mismatch,
            has_deformation_issue=has_deformation_issue,
            primary_issue_category=primary_category,
            bounds=bounds_info,
            bone_bindings=truncated_bindings,
            materials=materials,
            submeshes=submeshes,
            deformation=deformation,
            issues=all_issues,
            warnings=warnings,
        )
    except Exception as e:
        mesh_pkg.logger.error(f"Error during skinned_mesh_diagnostics for '{mesh_renderer_path}': {e}")
        return SkinnedMeshDiagnosticsResult(
            **bridge_error(e),
            mesh_renderer_path=mesh_renderer_path,
        )


__all__ = ["skinned_mesh_diagnostics"]
