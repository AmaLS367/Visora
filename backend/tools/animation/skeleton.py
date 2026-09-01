from typing import Any

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import BoneNode, BoneSearchResult, SkeletonMapperResult
from backend.tools.animation.analysis import (
    detect_duplicate_bones,
    detect_helper_bones,
    detect_mmd_bone_chains,
    map_humanoid_bones,
    match_bones_fuzzy,
)
from backend.tools.animation.scripts import _skeleton_hierarchy_code


async def _fetch_bone_hierarchy(root_transform_path: str) -> tuple[list[BoneNode], dict[str, Any]]:
    """
    Walks the bone hierarchy under a root transform via the Unity bridge and parses it into
    typed BoneNode DTOs, alongside the raw response dict (for avatar/required-bone data).

    Raises:
        RuntimeError: if Unity reports the hierarchy walk failed (root not found, etc.).
    """
    code = _skeleton_hierarchy_code(root_transform_path)
    resp = await animation_pkg.bridge.execute_code(code)

    result_data = resp.get("result")
    if not isinstance(result_data, dict):
        result_data = resp

    if not result_data.get("success", False):
        raise RuntimeError(str(result_data.get("error", "Unknown Unity skeleton inspection error")))

    raw_bones = result_data.get("bones", [])
    bones: list[BoneNode] = []
    if isinstance(raw_bones, list):
        for b in raw_bones:
            if isinstance(b, dict):
                bones.append(
                    BoneNode(
                        path=str(b.get("path", "")),
                        name=str(b.get("name", "")),
                        parent_path=b.get("parentPath"),
                        depth=int(b.get("depth", 0)),
                        child_count=int(b.get("childCount", 0)),
                        local_position=list(b.get("localPosition", [0.0, 0.0, 0.0])),
                        local_rotation_euler=list(b.get("localRotationEuler", [0.0, 0.0, 0.0])),
                        local_scale=list(b.get("localScale", [1.0, 1.0, 1.0])),
                    )
                )

    return bones, result_data


@mcp.tool()
async def skeleton_mapper(root_transform_path: str) -> SkeletonMapperResult:
    """
    Walks a real imported skeleton hierarchy, maps standard humanoid bones (via the Unity
    Avatar when present, or fuzzy name matching otherwise), and detects duplicate bone names,
    likely helper/dummy bones, and MMD-style primary/physics ('_D') bone chains.

    Args:
        root_transform_path: Hierarchical path in the active scene to the skeleton root GameObject.

    Returns:
        A SkeletonMapperResult detailing every bone found, the humanoid mapping, and rig diagnostics.
    """
    try:
        bones, result_data = await _fetch_bone_hierarchy(root_transform_path)

        duplicate_bones = detect_duplicate_bones(bones)
        helper_bones = detect_helper_bones(bones)
        mmd_bone_chains = detect_mmd_bone_chains(bones)

        raw_avatar_bones = result_data.get("avatarHumanBones", [])
        avatar_human_bones: list[tuple[str, str]] | None = None
        if isinstance(raw_avatar_bones, list) and raw_avatar_bones:
            avatar_human_bones = [
                (str(hb.get("humanName", "")), str(hb.get("boneName", "")))
                for hb in raw_avatar_bones
                if isinstance(hb, dict)
            ]

        required_names = [str(n) for n in result_data.get("requiredHumanBoneNames", [])]

        is_valid, mapping_source, mappings, missing_bones = map_humanoid_bones(
            bones=bones,
            required_names=required_names,
            avatar_human_bones=avatar_human_bones,
        )

        warnings: list[str] = []
        if not result_data.get("isHumanoidAvatar", False):
            warnings.append(
                "No Humanoid Avatar found under root; humanoid bone mapping is heuristic (fuzzy name matching)."
            )

        return SkeletonMapperResult(
            success=True,
            root_transform_path=root_transform_path,
            bone_count=len(bones),
            bones=bones,
            mapping_source=mapping_source,
            is_valid=is_valid,
            mappings=mappings,
            missing_bones=missing_bones,
            duplicate_bones=duplicate_bones,
            helper_bones=helper_bones,
            mmd_bone_chains=mmd_bone_chains,
            warnings=warnings,
        )
    except Exception as e:
        animation_pkg.logger.error(f"Error during skeleton_mapper for '{root_transform_path}': {e}")
        return SkeletonMapperResult(
            success=False,
            error=str(e),
            root_transform_path=root_transform_path,
        )


@mcp.tool()
async def find_bones(
    root_transform_path: str,
    query: str,
    exact_only: bool = False,
    max_results: int = 10,
) -> BoneSearchResult:
    """
    Finds bones under a skeleton root by exact and fuzzy name matching.

    Args:
        root_transform_path: Hierarchical path in the active scene to the skeleton root GameObject.
        query: Bone name to search for.
        exact_only: If True, only case-insensitive exact name matches are returned.
        max_results: Maximum number of matches to return.

    Returns:
        A BoneSearchResult with matching bones, best matches first.
    """
    try:
        bones, _ = await _fetch_bone_hierarchy(root_transform_path)
        matches = match_bones_fuzzy(query, bones, limit=max_results, exact_only=exact_only)
        return BoneSearchResult(
            success=True,
            root_transform_path=root_transform_path,
            query=query,
            matches=matches,
        )
    except Exception as e:
        animation_pkg.logger.error(f"Error during find_bones for '{root_transform_path}' query='{query}': {e}")
        return BoneSearchResult(
            success=False,
            error=str(e),
            root_transform_path=root_transform_path,
            query=query,
        )


__all__ = ["find_bones", "skeleton_mapper"]
