import asyncio
import base64
import io
import json
import logging
import math
import uuid
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import imageio.v2 as imageio
import numpy as np
from PIL import Image, UnidentifiedImageError

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import (
    CameraFramingDiagnosticsResult,
    FrameMotionMetrics,
    ProjectWorldPointsResult,
    SceneCameraInfo,
    ScreenPoint,
    ScreenshotResult,
    VideoFrame,
    VideoFrameSequence,
    VideoFramesResult,
    VideoMp4Result,
    VisualCapture,
    VisualComparisonResult,
    VisualInspectionResult,
)

logger = logging.getLogger("backend.tools.vision")
bridge = UnityBridge()


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _hierarchy_path_code(transform_expr: str) -> str:
    return f"""
var pathParts = new System.Collections.Generic.List<string>();
var currentTransform = {transform_expr};
while (currentTransform != null)
{{
    pathParts.Insert(0, currentTransform.name);
    currentTransform = currentTransform.parent;
}}
var hierarchyPath = string.Join("/", pathParts);
"""


def _list_scene_cameras_code() -> str:
    return f"""
var cameras = UnityEngine.Object.FindObjectsByType<UnityEngine.Camera>(UnityEngine.FindObjectsSortMode.None);
var items = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
foreach (var camera in cameras)
{{
    {_hierarchy_path_code("camera.transform")}
    items.Add(new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "name", camera.gameObject.name }},
        {{ "path", hierarchyPath }},
        {{ "enabled", camera.enabled }},
        {{ "active", camera.gameObject.activeInHierarchy }},
        {{ "tag", camera.gameObject.tag }},
        {{ "depth", camera.depth }},
        {{ "fieldOfView", camera.fieldOfView }},
        {{ "orthographic", camera.orthographic }},
        {{ "orthographicSize", camera.orthographicSize }},
    }});
}}
return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "cameras", items }},
}};
"""


def _camera_screenshot_code(camera_name: str, width: int, height: int) -> str:
    camera_name_literal = json.dumps(camera_name)
    return f"""
var cameraName = {camera_name_literal};
var width = {width};
var height = {height};
var warnings = new System.Collections.Generic.List<string>();
var gameObject = UnityEngine.GameObject.Find(cameraName);
var camera = gameObject != null ? gameObject.GetComponent<UnityEngine.Camera>() : null;
if (camera == null)
{{
    throw new System.Exception("Camera not found: " + cameraName);
}}
if (!camera.enabled)
{{
    warnings.Add("camera disabled");
}}

var previousTargetTexture = camera.targetTexture;
var previousActive = UnityEngine.RenderTexture.active;
var renderTexture = new UnityEngine.RenderTexture(width, height, 24, UnityEngine.RenderTextureFormat.ARGB32);
UnityEngine.Texture2D texture = null;

try
{{
    camera.targetTexture = renderTexture;
    UnityEngine.RenderTexture.active = renderTexture;
    camera.Render();

    texture = new UnityEngine.Texture2D(width, height, UnityEngine.TextureFormat.RGB24, false);
    texture.ReadPixels(new UnityEngine.Rect(0, 0, width, height), 0, 0);
    texture.Apply();

    var pngBytes = texture.EncodeToPNG();
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "imageBase64", System.Convert.ToBase64String(pngBytes) }},
        {{ "width", width }},
        {{ "height", height }},
        {{ "cameraName", cameraName }},
        {{ "warnings", warnings }},
    }};
}}
finally
{{
    camera.targetTexture = previousTargetTexture;
    UnityEngine.RenderTexture.active = previousActive;
    if (texture != null)
    {{
        UnityEngine.Object.DestroyImmediate(texture);
    }}
    renderTexture.Release();
    UnityEngine.Object.DestroyImmediate(renderTexture);
}}
"""


def _project_world_points_code(points: list[list[float]], camera_name: str) -> str:
    camera_name_literal = json.dumps(camera_name)
    point_rows = ",\n    ".join(
        f"new float[] {{ {float(point[0])}f, {float(point[1])}f, {float(point[2])}f }}" for point in points
    )
    return f"""
var cameraName = {camera_name_literal};
var cameraObject = UnityEngine.GameObject.Find(cameraName);
var camera = cameraObject != null ? cameraObject.GetComponent<UnityEngine.Camera>() : null;
if (camera == null)
{{
    throw new System.Exception("Camera not found: " + cameraName);
}}
var points = new float[][]
{{
    {point_rows}
}};
var projected = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
foreach (var point in points)
{{
    var viewportPoint = camera.WorldToViewportPoint(new UnityEngine.Vector3(point[0], point[1], point[2]));
    projected.Add(new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "x", viewportPoint.x }},
        {{ "y", viewportPoint.y }},
        {{ "z", viewportPoint.z }},
        {{ "isBehindCamera", viewportPoint.z < 0f }},
    }});
}}
return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "screenPoints", projected }},
}};
"""


def _camera_framing_diagnostics_code(subject_path: str, camera_name: str) -> str:
    subject_literal = json.dumps(subject_path)
    camera_literal = json.dumps(camera_name)
    return f"""
var subjectPath = {subject_literal};
var cameraName = {camera_literal};
var subject = UnityEngine.GameObject.Find(subjectPath);
if (subject == null)
{{
    throw new System.Exception("Subject not found: " + subjectPath);
}}
var cameraObject = UnityEngine.GameObject.Find(cameraName);
var camera = cameraObject != null ? cameraObject.GetComponent<UnityEngine.Camera>() : null;
if (camera == null)
{{
    throw new System.Exception("Camera not found: " + cameraName);
}}
var renderers = new System.Collections.Generic.List<UnityEngine.Renderer>();
renderers.AddRange(subject.GetComponentsInChildren<UnityEngine.Renderer>());
if (renderers.Count == 0)
{{
    throw new System.Exception("No renderers found for subject: " + subjectPath);
}}
var bounds = renderers[0].bounds;
for (var index = 1; index < renderers.Count; index++)
{{
    bounds.Encapsulate(renderers[index].bounds);
}}
var min = bounds.min;
var max = bounds.max;
var corners = new UnityEngine.Vector3[]
{{
    new UnityEngine.Vector3(min.x, min.y, min.z),
    new UnityEngine.Vector3(min.x, min.y, max.z),
    new UnityEngine.Vector3(min.x, max.y, min.z),
    new UnityEngine.Vector3(min.x, max.y, max.z),
    new UnityEngine.Vector3(max.x, min.y, min.z),
    new UnityEngine.Vector3(max.x, min.y, max.z),
    new UnityEngine.Vector3(max.x, max.y, min.z),
    new UnityEngine.Vector3(max.x, max.y, max.z),
}};
var minX = float.PositiveInfinity;
var minY = float.PositiveInfinity;
var maxX = float.NegativeInfinity;
var maxY = float.NegativeInfinity;
var behindCount = 0;
var depthClipped = false;
foreach (var corner in corners)
{{
    var viewportPoint = camera.WorldToViewportPoint(corner);
    minX = System.Math.Min(minX, viewportPoint.x);
    minY = System.Math.Min(minY, viewportPoint.y);
    maxX = System.Math.Max(maxX, viewportPoint.x);
    maxY = System.Math.Max(maxY, viewportPoint.y);
    if (viewportPoint.z < 0f)
    {{
        behindCount++;
    }}
    if (viewportPoint.z < camera.nearClipPlane || viewportPoint.z > camera.farClipPlane)
    {{
        depthClipped = true;
    }}
}}
var boundsWidth = System.Math.Max(0.0001f, maxX - minX);
var boundsHeight = System.Math.Max(0.0001f, maxY - minY);
var visibleWidth = System.Math.Max(0f, System.Math.Min(1f, maxX) - System.Math.Max(0f, minX));
var visibleHeight = System.Math.Max(0f, System.Math.Min(1f, maxY) - System.Math.Max(0f, minY));
var visibleRatio = (visibleWidth * visibleHeight) / (boundsWidth * boundsHeight);
var isBehindCamera = behindCount == corners.Length;
var isVisible = !isBehindCamera && visibleRatio > 0f;
var viewportClipped = minX < 0f || minY < 0f || maxX > 1f || maxY > 1f;
var isClipped = depthClipped || viewportClipped;
var framingStatus = "centered";
if (!isVisible)
{{
    framingStatus = "offscreen";
}}
else if (isClipped)
{{
    framingStatus = "clipped";
}}
else if (boundsHeight < 0.2f && boundsWidth < 0.2f)
{{
    framingStatus = "too_small";
}}
else if (boundsHeight > 0.95f || boundsWidth > 0.95f)
{{
    framingStatus = "too_large";
}}
var warnings = new System.Collections.Generic.List<string>();
if (isBehindCamera)
{{
    warnings.Add("subject is behind the camera");
}}
if (viewportClipped)
{{
    warnings.Add("subject viewport bounds extend outside the camera frame");
}}
if (depthClipped)
{{
    warnings.Add("subject intersects camera near/far clipping range");
}}
return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "subjectPath", subjectPath }},
    {{ "cameraName", cameraName }},
    {{ "viewportBounds", new float[] {{ minX, minY, maxX, maxY }} }},
    {{ "visibleRatio", visibleRatio }},
    {{ "isVisible", isVisible }},
    {{ "isBehindCamera", isBehindCamera }},
    {{ "isClipped", isClipped }},
    {{ "framingStatus", framingStatus }},
    {{ "warnings", warnings }},
}};
"""


def _diagnostic_scene_capture_code(subject_path: str | None, width: int, height: int) -> str:
    subject_literal = json.dumps(subject_path or "")
    return f"""
var subjectPath = {subject_literal};
var width = {width};
var height = {height};
var warnings = new System.Collections.Generic.List<string>();
var diagnosticRoot = new UnityEngine.GameObject("Visora Diagnostic Capture");
var cameraObject = new UnityEngine.GameObject("Visora Diagnostic Camera");
var keyLightObject = new UnityEngine.GameObject("Visora Diagnostic Key Light");
var fillLightObject = new UnityEngine.GameObject("Visora Diagnostic Fill Light");
cameraObject.transform.SetParent(diagnosticRoot.transform);
keyLightObject.transform.SetParent(diagnosticRoot.transform);
fillLightObject.transform.SetParent(diagnosticRoot.transform);
UnityEngine.Camera diagnosticCamera = null;
UnityEngine.Light keyLight = null;
UnityEngine.Light fillLight = null;
UnityEngine.Texture2D texture = null;
UnityEngine.RenderTexture renderTexture = null;

var previousActive = UnityEngine.RenderTexture.active;
var previousAmbientMode = UnityEngine.RenderSettings.ambientMode;
var previousAmbientLight = UnityEngine.RenderSettings.ambientLight;
var previousAmbientIntensity = UnityEngine.RenderSettings.ambientIntensity;
var previousFog = UnityEngine.RenderSettings.fog;

try
{{
    var renderers = new System.Collections.Generic.List<UnityEngine.Renderer>();
    if (!string.IsNullOrEmpty(subjectPath))
    {{
        var subject = UnityEngine.GameObject.Find(subjectPath);
        if (subject == null)
        {{
            warnings.Add("subject not found; diagnostic capture uses all visible renderers");
        }}
        else
        {{
            renderers.AddRange(subject.GetComponentsInChildren<UnityEngine.Renderer>());
        }}
    }}

    if (renderers.Count == 0)
    {{
        renderers.AddRange(UnityEngine.Object.FindObjectsByType<UnityEngine.Renderer>(UnityEngine.FindObjectsSortMode.None));
    }}

    if (renderers.Count == 0)
    {{
        throw new System.Exception("No renderers found for diagnostic visual inspection");
    }}

    var bounds = renderers[0].bounds;
    for (var index = 1; index < renderers.Count; index++)
    {{
        bounds.Encapsulate(renderers[index].bounds);
    }}

    var size = bounds.size;
    var radius = System.Math.Max(0.5f, size.magnitude * 0.5f);
    var aspect = (float)width / (float)height;
    var orthographicSize = System.Math.Max(size.y * 0.55f, size.x / (2f * aspect)) * 1.15f;
    orthographicSize = System.Math.Max(orthographicSize, 0.75f);
    var center = bounds.center;
    var distance = System.Math.Max(radius * 4f, 4f);

    diagnosticCamera = cameraObject.AddComponent<UnityEngine.Camera>();
    diagnosticCamera.name = "Visora Diagnostic Camera";
    diagnosticCamera.clearFlags = UnityEngine.CameraClearFlags.SolidColor;
    diagnosticCamera.backgroundColor = new UnityEngine.Color(0.74f, 0.76f, 0.78f, 1f);
    diagnosticCamera.cullingMask = ~0;
    diagnosticCamera.orthographic = true;
    diagnosticCamera.orthographicSize = orthographicSize;
    diagnosticCamera.nearClipPlane = 0.01f;
    diagnosticCamera.farClipPlane = 1000f;
    diagnosticCamera.allowHDR = false;
    diagnosticCamera.transform.position = center + new UnityEngine.Vector3(0f, 0f, -distance);
    diagnosticCamera.transform.LookAt(center);

    var hdCameraType = System.Type.GetType("UnityEngine.Rendering.HighDefinition.HDAdditionalCameraData, Unity.RenderPipelines.HighDefinition.Runtime");
    if (hdCameraType != null)
    {{
        var hdCameraData = cameraObject.AddComponent(hdCameraType);
        var volumeLayerMaskField = hdCameraType.GetField("volumeLayerMask");
        if (volumeLayerMaskField != null)
        {{
            volumeLayerMaskField.SetValue(hdCameraData, (UnityEngine.LayerMask)0);
            warnings.Add("diagnostic_lit disables HDRP volumeLayerMask to avoid scene depth-of-field and exposure volumes");
        }}
        var antialiasingField = hdCameraType.GetField("antialiasing");
        if (antialiasingField != null)
        {{
            antialiasingField.SetValue(hdCameraData, System.Enum.ToObject(antialiasingField.FieldType, 0));
        }}
    }}

    keyLight = keyLightObject.AddComponent<UnityEngine.Light>();
    keyLight.type = UnityEngine.LightType.Directional;
    keyLight.intensity = 2.1f;
    keyLight.transform.rotation = UnityEngine.Quaternion.Euler(45f, -35f, 0f);
    fillLight = fillLightObject.AddComponent<UnityEngine.Light>();
    fillLight.type = UnityEngine.LightType.Directional;
    fillLight.intensity = 0.9f;
    fillLight.transform.rotation = UnityEngine.Quaternion.Euler(15f, 145f, 0f);

    UnityEngine.RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
    UnityEngine.RenderSettings.ambientLight = new UnityEngine.Color(0.85f, 0.85f, 0.85f, 1f);
    UnityEngine.RenderSettings.ambientIntensity = 1.8f;
    UnityEngine.RenderSettings.fog = false;

    renderTexture = new UnityEngine.RenderTexture(width, height, 24, UnityEngine.RenderTextureFormat.ARGB32);
    diagnosticCamera.targetTexture = renderTexture;
    UnityEngine.RenderTexture.active = renderTexture;
    diagnosticCamera.Render();

    texture = new UnityEngine.Texture2D(width, height, UnityEngine.TextureFormat.RGB24, false);
    texture.ReadPixels(new UnityEngine.Rect(0, 0, width, height), 0, 0);
    texture.Apply();

    var pngBytes = texture.EncodeToPNG();
    warnings.Add("diagnostic_lit uses temporary camera, neutral background, temporary lighting, and disabled fog; do not treat it as final game lighting");
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "imageBase64", System.Convert.ToBase64String(pngBytes) }},
        {{ "width", width }},
        {{ "height", height }},
        {{ "cameraName", "Visora Diagnostic Camera" }},
        {{ "mode", "diagnostic_lit" }},
        {{ "subjectPath", subjectPath }},
        {{ "warnings", warnings }},
    }};
}}
finally
{{
    UnityEngine.RenderTexture.active = previousActive;
    UnityEngine.RenderSettings.ambientMode = previousAmbientMode;
    UnityEngine.RenderSettings.ambientLight = previousAmbientLight;
    UnityEngine.RenderSettings.ambientIntensity = previousAmbientIntensity;
    UnityEngine.RenderSettings.fog = previousFog;
    if (texture != null)
    {{
        UnityEngine.Object.DestroyImmediate(texture);
    }}
    if (renderTexture != null)
    {{
        renderTexture.Release();
        UnityEngine.Object.DestroyImmediate(renderTexture);
    }}
    UnityEngine.Object.DestroyImmediate(diagnosticRoot);
}}
"""


def _extract_result_payload(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error") or response.get("errorMessage")
    if error:
        raise RuntimeError(str(error))
    if response.get("success") is False:
        raise RuntimeError("Unity bridge reported an unsuccessful execution")

    payload = response.get("result", response)
    if isinstance(payload, str):
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise RuntimeError("Unity execution returned a non-object JSON payload")
        payload = parsed
    if not isinstance(payload, dict):
        raise RuntimeError("Unity execution returned an unsupported payload")
    return payload


def _decode_image(image_base64: str) -> Image.Image:
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
        image = Image.open(io.BytesIO(image_bytes))
        return image.convert("RGB")
    except (ValueError, UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid base64 image data") from exc


def _normalize_threshold(threshold: int) -> int:
    return max(0, min(255, threshold))


def _validate_video_request(
    duration_seconds: float,
    fps: int,
    width: int,
    height: int,
    max_fps: int,
) -> str | None:
    if duration_seconds < 0.1 or duration_seconds > 10.0:
        return "duration_seconds must be between 0.1 and 10.0"
    if fps < 1 or fps > max_fps:
        return f"fps must be between 1 and {max_fps}"
    if width <= 0 or height <= 0:
        return "width and height must be positive integers"
    if width > 1920 or height > 1080:
        return "width and height must not exceed 1920x1080"
    if math.ceil(duration_seconds * fps) > 120:
        return "video capture must not exceed 120 sampled frames"
    return None


def _payload_warnings(payload: dict[str, Any]) -> list[str]:
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        return [str(warnings)]
    return [str(warning) for warning in warnings]


def _payload_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _frame_count(duration_seconds: float, fps: int) -> int:
    return max(1, math.ceil(duration_seconds * fps))


def _motion_metric_from_frames(
    from_frame: int, to_frame: int, before_base64: str, after_base64: str
) -> FrameMotionMetrics:
    comparison = compare_screenshots(before_base64, after_base64)
    return FrameMotionMetrics(
        from_frame=from_frame,
        to_frame=to_frame,
        changed_pixel_ratio=comparison.changed_pixel_ratio,
        mean_delta=comparison.mean_delta,
        max_delta=comparison.max_delta,
        changed_bounds=comparison.changed_bounds,
    )


def _encode_frames_to_mp4(frame_images_base64: list[str], fps: int, width: int, height: int) -> tuple[bytes, Path]:
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / f"visora-video-{uuid.uuid4().hex}.mp4"

    with cast(Any, imageio.get_writer(output_path, fps=fps, codec="libx264", macro_block_size=None)) as writer:
        for image_base64 in frame_images_base64:
            image = _decode_image(image_base64).resize((width, height))
            writer.append_data(np.asarray(image))

    return output_path.read_bytes(), output_path.resolve()


def _capture_from_payload(mode: str, payload: dict[str, Any], fallback_camera_name: str) -> VisualCapture:
    image_base64 = payload.get("imageBase64") or payload.get("image_base64")
    if not isinstance(image_base64, str) or not image_base64:
        raise RuntimeError("Unity visual capture response did not include imageBase64")
    return VisualCapture(
        mode=mode,
        image_base64=image_base64,
        width=int(payload["width"]),
        height=int(payload["height"]),
        camera_name=str(payload.get("cameraName", fallback_camera_name)),
        warnings=_payload_warnings(payload),
    )


@mcp.tool()
async def list_scene_cameras() -> list[SceneCameraInfo]:
    """
    Lists active Unity scene cameras so agents can choose a real camera before rendering or projection.

    Returns:
        A compact list of scene camera metadata.
    """
    response = await bridge.execute_code(_list_scene_cameras_code())
    payload = _extract_result_payload(response)
    cameras = payload.get("cameras", [])
    if not isinstance(cameras, list):
        raise RuntimeError("Unity camera inventory response did not include cameras")

    return [
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
        for camera in cameras
        if isinstance(camera, dict)
    ]


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
    if width <= 0 or height <= 0:
        return ScreenshotResult(success=False, error="width and height must be positive integers")

    try:
        response = await bridge.execute_code(_camera_screenshot_code(camera_name, width, height))
        payload = _extract_result_payload(response)
        image_base64 = payload.get("imageBase64") or payload.get("image_base64")
        if not isinstance(image_base64, str) or not image_base64:
            return ScreenshotResult(success=False, error="Unity screenshot response did not include imageBase64")

        return ScreenshotResult(
            success=True,
            image_base64=image_base64,
            width=int(payload.get("width", width)),
            height=int(payload.get("height", height)),
            camera_name=str(payload.get("cameraName", camera_name)),
            warnings=_payload_warnings(payload),
        )
    except Exception as exc:
        logger.exception("Screenshot capture failed")
        return ScreenshotResult(success=False, error=str(exc))


@mcp.tool()
def compare_screenshots(
    before_image_base64: str,
    after_image_base64: str,
    threshold: int = 8,
) -> VisualComparisonResult:
    """
    Compares two screenshots and returns compact visual-change diagnostics.

    Args:
        before_image_base64: Base64 encoded PNG/JPEG image before a scene change.
        after_image_base64: Base64 encoded PNG/JPEG image after a scene change.
        threshold: Per-channel delta threshold required to count a pixel as changed.

    Returns:
        A VisualComparisonResult with changed-pixel metrics and changed bounds.
    """
    try:
        before = _decode_image(before_image_base64)
        after = _decode_image(after_image_base64)
    except ValueError as exc:
        return VisualComparisonResult(success=False, error=str(exc))

    if before.size != after.size:
        return VisualComparisonResult(
            success=False,
            error="screenshots must have matching dimensions",
            same_dimensions=False,
        )

    threshold = _normalize_threshold(threshold)
    width, height = before.size
    total_pixels = width * height
    changed_pixels = 0
    delta_sum = 0
    max_delta = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    before_pixels = list(before.get_flattened_data())
    after_pixels = list(after.get_flattened_data())
    for index, (before_pixel_raw, after_pixel_raw) in enumerate(zip(before_pixels, after_pixels, strict=True)):
        before_pixel = cast(tuple[int, int, int], before_pixel_raw)
        after_pixel = cast(tuple[int, int, int], after_pixel_raw)
        x = index % width
        y = index // width
        deltas = [abs(before_pixel[channel] - after_pixel[channel]) for channel in range(3)]
        pixel_max_delta = max(deltas)
        max_delta = max(max_delta, pixel_max_delta)
        delta_sum += sum(deltas)
        if pixel_max_delta > threshold:
            changed_pixels += 1
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    changed_bounds = [min_x, min_y, max_x, max_y] if changed_pixels else None
    return VisualComparisonResult(
        success=True,
        same_dimensions=True,
        width=width,
        height=height,
        changed_pixel_ratio=changed_pixels / total_pixels if total_pixels else 0.0,
        mean_delta=delta_sum / (total_pixels * 3) if total_pixels else 0.0,
        max_delta=max_delta,
        changed_bounds=changed_bounds,
    )


@mcp.tool()
async def inspect_scene_visual(
    subject_path: str | None = None,
    camera_name: str = "Main Camera",
    width: int = 1280,
    height: int = 720,
) -> VisualInspectionResult:
    """
    Captures a scene with both authored camera rendering and diagnostic inspection rendering.

    Use this when the user asks what is visible in a Unity scene, whether a model/pose/animation looks correct,
    or when production lighting, environment, or final camera framing may be incomplete. Agents should inspect
    diagnostic_lit for model and animation visibility before drawing conclusions from game_camera darkness.
    """
    if width <= 0 or height <= 0:
        return VisualInspectionResult(
            success=False,
            error="width and height must be positive integers",
            subject_path=subject_path,
            recommended_interpretation="No captures were produced because the requested dimensions were invalid.",
        )

    captures: list[VisualCapture] = []
    warnings: list[str] = [
        "Use diagnostic_lit for model, pose, rig, and animation inspection when authored lighting is incomplete.",
        "Use game_camera for final player-facing composition only; darkness there is not proof that the subject is missing.",
    ]

    try:
        game_response = await bridge.execute_code(_camera_screenshot_code(camera_name, width, height))
        game_payload = _extract_result_payload(game_response)
        captures.append(_capture_from_payload("game_camera", game_payload, camera_name))
        warnings.extend(f"game_camera: {warning}" for warning in _payload_warnings(game_payload))
    except Exception as exc:
        logger.warning("Game camera visual inspection capture failed: %s", exc)
        warnings.append(f"game camera capture failed: {exc}")

    try:
        diagnostic_response = await bridge.execute_code(_diagnostic_scene_capture_code(subject_path, width, height))
        diagnostic_payload = _extract_result_payload(diagnostic_response)
        captures.append(_capture_from_payload("diagnostic_lit", diagnostic_payload, "Visora Diagnostic Camera"))
        warnings.extend(f"diagnostic_lit: {warning}" for warning in _payload_warnings(diagnostic_payload))
    except Exception as exc:
        logger.exception("Diagnostic visual inspection capture failed")
        warnings.append(f"diagnostic capture failed: {exc}")

    if not captures:
        return VisualInspectionResult(
            success=False,
            error="all visual inspection captures failed",
            subject_path=subject_path,
            captures=[],
            warnings=warnings,
            recommended_interpretation=(
                "No visual capture was available. Check Unity bridge status, scene renderers, and camera names before "
                "making visual conclusions."
            ),
        )

    return VisualInspectionResult(
        success=True,
        subject_path=subject_path,
        captures=captures,
        warnings=warnings,
        recommended_interpretation=(
            "Use diagnostic_lit first to inspect the actual model, pose, animation, mesh, and silhouette. "
            "Do not conclude the scene is empty, broken, or missing from a dark game_camera capture alone. "
            "Use game_camera only for authored lighting, final composition, and player-facing framing checks."
        ),
    )


async def _capture_video_frame(  # noqa: PLR0913
    frame_index: int,
    timestamp_seconds: float,
    camera_name: str,
    subject_path: str | None,
    mode: str,
    width: int,
    height: int,
) -> VideoFrame:
    if mode == "diagnostic_lit":
        response = await bridge.execute_code(_diagnostic_scene_capture_code(subject_path, width, height))
        fallback_camera_name = "Visora Diagnostic Camera"
    elif mode == "game_camera":
        response = await bridge.execute_code(_camera_screenshot_code(camera_name, width, height))
        fallback_camera_name = camera_name
    else:
        raise ValueError("mode must be either diagnostic_lit or game_camera")

    payload = _extract_result_payload(response)
    image_base64 = payload.get("imageBase64") or payload.get("image_base64")
    if not isinstance(image_base64, str) or not image_base64:
        raise RuntimeError("Unity video frame response did not include imageBase64")

    return VideoFrame(
        frame_index=frame_index,
        timestamp_seconds=timestamp_seconds,
        camera_name=str(payload.get("cameraName", fallback_camera_name)),
        mode=mode,
        image_base64=image_base64,
        width=int(payload.get("width", width)),
        height=int(payload.get("height", height)),
        warnings=_payload_warnings(payload),
    )


@mcp.tool()
async def get_video_frames(  # noqa: PLR0912, PLR0913, PLR0915
    camera_names: list[str] | None = None,
    subject_path: str | None = None,
    mode: str = "diagnostic_lit",
    duration_seconds: float = 2.0,
    fps: int = 6,
    width: int = 1280,
    height: int = 720,
    enter_play_mode: bool = True,
    include_motion_metrics: bool = True,
) -> VideoFramesResult:
    """
    Captures sampled camera frames for agents that reason over frame sequences instead of raw video.
    """
    validation_error = _validate_video_request(duration_seconds, fps, width, height, max_fps=12)
    if validation_error is not None:
        return VideoFramesResult(
            success=False,
            error=validation_error,
            recommended_interpretation="No frames were captured because the request exceeded v1 validation limits.",
        )
    if mode not in {"diagnostic_lit", "game_camera"}:
        return VideoFramesResult(
            success=False,
            error="mode must be either diagnostic_lit or game_camera",
            recommended_interpretation="Use diagnostic_lit for model motion inspection or game_camera for authored camera checks.",
        )

    camera_names = camera_names or ["Main Camera"]
    count = _frame_count(duration_seconds, fps)
    warnings: list[str] = [
        "Use sampled frames and motion_metrics for temporal reasoning when the model cannot inspect MP4 directly.",
    ]
    sequences: list[VideoFrameSequence] = []
    started_play_mode = False

    try:
        state = await bridge.get_editor_state()
        was_playing = bool(state.get("isPlaying", False))
        if enter_play_mode and not was_playing:
            await bridge.set_play_mode(True)
            started_play_mode = True
            await _sleep(0.5)

        for camera_name in camera_names:
            frames: list[VideoFrame] = []
            sequence_warnings: list[str] = []
            for frame_index in range(count):
                timestamp_seconds = frame_index / fps
                try:
                    frame = await _capture_video_frame(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        camera_name=camera_name,
                        subject_path=subject_path,
                        mode=mode,
                        width=width,
                        height=height,
                    )
                    frames.append(frame)
                    sequence_warnings.extend(f"frame {frame_index}: {warning}" for warning in frame.warnings)
                except Exception as exc:
                    logger.exception("Video frame capture failed")
                    sequence_warnings.append(f"frame {frame_index} capture failed: {exc}")
                    break

                if frame_index < count - 1:
                    await _sleep(1 / fps)

            motion_metrics: list[FrameMotionMetrics] = []
            if include_motion_metrics:
                motion_metrics = [
                    _motion_metric_from_frames(
                        from_frame=previous.frame_index,
                        to_frame=current.frame_index,
                        before_base64=previous.image_base64,
                        after_base64=current.image_base64,
                    )
                    for previous, current in pairwise(frames)
                ]
                if motion_metrics and max(metric.changed_pixel_ratio for metric in motion_metrics) < 0.001:
                    sequence_warnings.append("near-zero visual motion detected across sampled frames")

            sequences.append(
                VideoFrameSequence(
                    camera_name=camera_name,
                    mode=mode,
                    duration_seconds=duration_seconds,
                    fps=fps,
                    frames=frames,
                    motion_metrics=motion_metrics,
                    warnings=sequence_warnings,
                ),
            )

        success = any(sequence.frames for sequence in sequences)
        result = VideoFramesResult(
            success=success,
            error=None if success else "no video frames were captured",
            sequences=sequences,
            warnings=warnings,
            recommended_interpretation=(
                "Use diagnostic_lit frames for model and animation motion. Use motion_metrics to find changed intervals; "
                "use MP4 only when the consuming model can inspect video directly."
            ),
        )
        return result
    except Exception as exc:
        logger.exception("Video frame sequence capture failed")
        result = VideoFramesResult(
            success=False,
            error=str(exc),
            sequences=sequences,
            warnings=warnings,
            recommended_interpretation="Video frame capture failed before Visora could produce a reliable sequence.",
        )
        return result
    finally:
        if started_play_mode:
            try:
                await bridge.set_play_mode(False)
            except Exception as exc:
                logger.exception("Failed to restore Play Mode after video capture")
                restore_warning = f"failed to restore play mode: {exc}"
                warnings.append(restore_warning)
                if "result" in locals():
                    result.warnings.append(restore_warning)


@mcp.tool()
async def get_video_mp4(  # noqa: PLR0913
    camera_name: str = "Main Camera",
    subject_path: str | None = None,
    mode: str = "diagnostic_lit",
    duration_seconds: float = 2.0,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
    enter_play_mode: bool = True,
) -> VideoMp4Result:
    """
    Captures a short camera video and returns MP4 bytes for video-capable models.
    """
    validation_error = _validate_video_request(duration_seconds, fps, width, height, max_fps=30)
    if validation_error is not None:
        return VideoMp4Result(
            success=False,
            error=validation_error,
            camera_name=camera_name,
            mode=mode,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
        )

    frames_result = await get_video_frames(
        camera_names=[camera_name],
        subject_path=subject_path,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        enter_play_mode=enter_play_mode,
        include_motion_metrics=False,
    )
    if not frames_result.success or not frames_result.sequences or not frames_result.sequences[0].frames:
        return VideoMp4Result(
            success=False,
            error=frames_result.error or "no frames available for MP4 export",
            camera_name=camera_name,
            mode=mode,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
            warnings=frames_result.warnings,
        )

    frame_images = [frame.image_base64 for frame in frames_result.sequences[0].frames]
    try:
        video_bytes, artifact_path = _encode_frames_to_mp4(frame_images, fps, width, height)
    except Exception as exc:
        logger.exception("MP4 export failed")
        return VideoMp4Result(
            success=False,
            error=str(exc),
            camera_name=camera_name,
            mode=mode,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
            warnings=frames_result.warnings,
        )

    return VideoMp4Result(
        success=True,
        video_base64=base64.b64encode(video_bytes).decode("ascii"),
        artifact_path=str(artifact_path),
        camera_name=camera_name,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        warnings=frames_result.warnings,
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
        A ProjectWorldPointsResult with a list of 2D screen positions.
    """
    if any(len(point) != 3 for point in points):
        return ProjectWorldPointsResult(
            success=False,
            error="each world point must contain exactly 3 coordinates",
        )

    try:
        response = await bridge.execute_code(_project_world_points_code(points, camera_name))
        payload = _extract_result_payload(response)
        raw_points = payload.get("screenPoints", payload.get("screen_points", []))
        if not isinstance(raw_points, list):
            return ProjectWorldPointsResult(
                success=False, error="Unity projection response did not include screenPoints"
            )

        return ProjectWorldPointsResult(
            success=True,
            screen_points=[
                ScreenPoint(
                    x=float(point.get("x", 0.0)),
                    y=float(point.get("y", 0.0)),
                    z=float(point.get("z", 0.0)),
                    is_behind_camera=bool(point.get("isBehindCamera", point.get("is_behind_camera", False))),
                )
                for point in raw_points
                if isinstance(point, dict)
            ],
        )
    except Exception as exc:
        logger.exception("World point projection failed")
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
        A CameraFramingDiagnosticsResult with viewport bounds and framing status.
    """
    try:
        response = await bridge.execute_code(_camera_framing_diagnostics_code(subject_path, camera_name))
        payload = _extract_result_payload(response)
        viewport_bounds = payload.get("viewportBounds", payload.get("viewport_bounds"))
        return CameraFramingDiagnosticsResult(
            success=True,
            subject_path=str(payload.get("subjectPath", subject_path)),
            camera_name=str(payload.get("cameraName", camera_name)),
            viewport_bounds=[float(value) for value in viewport_bounds] if isinstance(viewport_bounds, list) else None,
            visible_ratio=float(payload.get("visibleRatio", payload.get("visible_ratio", 0.0))),
            is_visible=bool(payload.get("isVisible", payload.get("is_visible", False))),
            is_behind_camera=bool(payload.get("isBehindCamera", payload.get("is_behind_camera", False))),
            is_clipped=bool(payload.get("isClipped", payload.get("is_clipped", False))),
            framing_status=str(payload.get("framingStatus", payload.get("framing_status", "unknown"))),
            warnings=_payload_warnings(payload),
        )
    except Exception as exc:
        logger.exception("Camera framing diagnostics failed")
        return CameraFramingDiagnosticsResult(
            success=False,
            error=str(exc),
            subject_path=subject_path,
            camera_name=camera_name,
            is_visible=False,
            warnings=[],
        )
