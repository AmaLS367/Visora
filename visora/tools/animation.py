from visora.app import mcp
from visora.schemas import ClipInspectorResult, SkeletonMapperResult


@mcp.tool()
async def clip_inspector(clip_path: str) -> ClipInspectorResult:
    """
    Inspects an animation clip's metadata and properties inside the Unity project assets.

    Args:
        clip_path: The project-relative path to the animation clip asset (e.g., "Assets/Animations/RoverStomp.anim").

    Returns:
        A ClipInspectorResult containing animation duration, frame rate, loop configuration, and curve metrics.
    """
    # Empty decorated stub - no implementation yet
    return ClipInspectorResult(success=True)


@mcp.tool()
async def skeleton_mapper(root_transform_path: str) -> SkeletonMapperResult:
    """
    Validates and maps an avatar/character bone hierarchy relative to a root transform.

    Args:
        root_transform_path: Hierarchical path in the active scene to the skeleton root GameObject.

    Returns:
        A SkeletonMapperResult detailing mapped transforms and missing required humanoid bones.
    """
    # Empty decorated stub - no implementation yet
    return SkeletonMapperResult(success=True)
