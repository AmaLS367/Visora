from visora.schemas import ProjectWorldPointsResult, ScreenshotResult
from visora.server import mcp


@mcp.tool()
async def screenshot(
    camera_name: str = "Main Camera",
    width: int = 1920,
    height: int = 1080,
) -> ScreenshotResult:
    """
    Captures a high-resolution screenshot from the specified editor or gameplay camera.

    Args:
        camera_name: Name of the Unity camera in the active scene to render from.
        width: Desired width of the screenshot in pixels.
        height: Desired height of the screenshot in pixels.

    Returns:
        A ScreenshotResult object containing base64-encoded image data or error details.
    """
    # Empty decorated stub - no implementation yet
    return ScreenshotResult(success=True)


@mcp.tool()
async def project_world_points(
    points: list[list[float]],
    camera_name: str = "Main Camera",
) -> ProjectWorldPointsResult:
    """
    Projects 3D world coordinates onto the 2D screen coordinate viewport of a camera.

    Args:
        points: A list of 3D world points, where each point is a list of [x, y, z] floats.
        camera_name: Name of the Unity camera used to compute projections.

    Returns:
        A ProjectWorldPointsResult with a list of 2D screen positions.
    """
    # Empty decorated stub - no implementation yet
    return ProjectWorldPointsResult(success=True)
