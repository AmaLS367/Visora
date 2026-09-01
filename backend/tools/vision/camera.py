from typing import Any

import backend.tools.vision as vision_pkg
from backend.app import mcp
from backend.schemas import (
    CameraFramingDiagnosticsResult,
    ListSceneCamerasResult,
    ProjectWorldPointsResult,
    SceneCameraInfo,
    ScreenPoint,
)
from backend.tools.vision.image_utils import (
    _extract_result_payload,
    _payload_float,
    _payload_warnings,
)
from backend.tools.vision.scripts import (
    _camera_framing_diagnostics_code,
    _list_scene_cameras_code,
    _project_world_points_code,
)


@mcp.tool()
async def list_scene_cameras() -> ListSceneCamerasResult:
    """
    Lists active Unity scene cameras so agents can choose a real camera before rendering or projection.

    Returns:
        A ListSceneCamerasResult containing total camera count, detailed camera metadata, and warnings.
    """
    try:
        response = await vision_pkg.bridge.execute_capability(
            _list_scene_cameras_code(), native_path="/api/visora/camera/list"
        )
        payload = _extract_result_payload(response)
        if not payload.get("success", True) or payload.get("error"):
            return ListSceneCamerasResult(
                success=False,
                error=str(payload.get("error", "Failed to list scene cameras")),
                camera_count=0,
                cameras=[],
                warnings=_payload_warnings(payload),
            )

        raw_cameras = payload.get("cameras", [])
        if not isinstance(raw_cameras, list):
            return ListSceneCamerasResult(
                success=False,
                error="Unity camera inventory response did not include a valid cameras list",
                camera_count=0,
                cameras=[],
                warnings=_payload_warnings(payload),
            )

        cameras = [
            SceneCameraInfo(
                name=str(camera.get("name", "")),
                path=str(camera.get("path", "")),
                enabled=bool(camera.get("enabled", False)),
                active=bool(camera.get("active", False)),
                tag=str(camera.get("tag", "")),
                depth=_payload_float(camera.get("depth")),
                field_of_view=_payload_float(camera.get("fieldOfView", camera.get("field_of_view"))),
                orthographic=bool(camera.get("orthographic", False)),
                orthographic_size=_payload_float(camera.get("orthographicSize", camera.get("orthographic_size"))),
            )
            for camera in raw_cameras
            if isinstance(camera, dict)
        ]

        return ListSceneCamerasResult(
            success=True,
            camera_count=len(cameras),
            cameras=cameras,
            warnings=_payload_warnings(payload),
        )
    except Exception as exc:
        vision_pkg.logger.exception("Listing scene cameras failed")
        return ListSceneCamerasResult(
            success=False,
            error=str(exc),
            camera_count=0,
            cameras=[],
            warnings=[],
        )


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
        A ProjectWorldPointsResult with a list of 2D screen positions and depth information.
    """
    if any(len(point) != 3 for point in points):
        return ProjectWorldPointsResult(
            success=False,
            error="each world point must contain exactly 3 coordinates",
        )

    try:
        response = await vision_pkg.bridge.execute_capability(
            _project_world_points_code(points, camera_name),
            native_path="/api/visora/camera/project",
            native_payload={"cameraName": camera_name, "points": points},
        )
        payload = _extract_result_payload(response)
        if not payload.get("success", True) or payload.get("error"):
            return ProjectWorldPointsResult(
                success=False,
                error=str(payload.get("error", "World point projection failed")),
            )

        raw_points = payload.get("screenPoints", payload.get("screen_points", []))
        if not isinstance(raw_points, list):
            return ProjectWorldPointsResult(
                success=False, error="Unity projection response did not include screenPoints"
            )

        return ProjectWorldPointsResult(
            success=True,
            screen_points=[
                ScreenPoint(
                    x=_payload_float(point.get("x")),
                    y=_payload_float(point.get("y")),
                    z=_payload_float(point.get("z")),
                    is_behind_camera=bool(point.get("isBehindCamera", point.get("is_behind_camera", False))),
                )
                for point in raw_points
                if isinstance(point, dict)
            ],
        )
    except Exception as exc:
        vision_pkg.logger.exception("World point projection failed")
        return ProjectWorldPointsResult(success=False, error=str(exc))


@mcp.tool()
async def diagnose_camera_framing(
    subject_path: str,
    camera_name: str = "Main Camera",
) -> CameraFramingDiagnosticsResult:
    """
    Diagnoses whether a subject renderer bounds are visible and well framed by a Unity camera.

    Args:
        subject_path: Hierarchy path or GameObject name for the inspected subject.
        camera_name: Name of the Unity camera used for viewport projection.

    Returns:
        A CameraFramingDiagnosticsResult with viewport bounds, framing status, and clipping metrics.
    """
    try:
        response = await vision_pkg.bridge.execute_capability(
            _camera_framing_diagnostics_code(subject_path, camera_name),
            native_path="/api/visora/camera/framing",
            native_payload={"cameraName": camera_name, "subjectPath": subject_path},
        )
        payload = _extract_result_payload(response)
        if not payload.get("success", True) or payload.get("error"):
            return CameraFramingDiagnosticsResult(
                success=False,
                error=str(payload.get("error", "Camera framing diagnostics failed")),
                subject_path=subject_path,
                camera_name=camera_name,
                is_visible=False,
                warnings=_payload_warnings(payload),
            )

        viewport_bounds = payload.get("viewportBounds", payload.get("viewport_bounds"))
        return CameraFramingDiagnosticsResult(
            success=True,
            subject_path=str(payload.get("subjectPath", subject_path)),
            camera_name=str(payload.get("cameraName", camera_name)),
            viewport_bounds=[_payload_float(value) for value in viewport_bounds]
            if isinstance(viewport_bounds, list)
            else None,
            visible_ratio=_payload_float(payload.get("visibleRatio", payload.get("visible_ratio"))),
            is_visible=bool(payload.get("isVisible", payload.get("is_visible", False))),
            is_behind_camera=bool(payload.get("isBehindCamera", payload.get("is_behind_camera", False))),
            is_clipped=bool(payload.get("isClipped", payload.get("is_clipped", False))),
            framing_status=str(payload.get("framingStatus", payload.get("framing_status", "unknown"))),
            warnings=_payload_warnings(payload),
        )
    except Exception as exc:
        vision_pkg.logger.exception("Camera framing diagnostics failed")
        return CameraFramingDiagnosticsResult(
            success=False,
            error=str(exc),
            subject_path=subject_path,
            camera_name=camera_name,
            is_visible=False,
            warnings=[],
        )


__all__ = [
    "diagnose_camera_framing",
    "list_scene_cameras",
    "project_world_points",
]
