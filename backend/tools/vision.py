import base64
import io
import json
import logging
from typing import Any, cast

from PIL import Image, UnidentifiedImageError

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import (
    ProjectWorldPointsResult,
    ScreenshotResult,
    VisualCapture,
    VisualComparisonResult,
    VisualInspectionResult,
)

logger = logging.getLogger("backend.tools.vision")
bridge = UnityBridge()


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


def _payload_warnings(payload: dict[str, Any]) -> list[str]:
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        return [str(warnings)]
    return [str(warning) for warning in warnings]


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
