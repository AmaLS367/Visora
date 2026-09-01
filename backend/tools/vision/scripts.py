import json


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
    point_rows = ",\n    ".join(f"new float[] {{ {point[0]}f, {point[1]}f, {point[2]}f }}" for point in points)
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
