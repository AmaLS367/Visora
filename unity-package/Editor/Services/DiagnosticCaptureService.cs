using System;
using System.Collections;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace Visora.Editor.Services
{
    /// <summary>
    /// Neutral, temporary lighting rig used to inspect geometry and motion without the scene's own
    /// lighting, post-processing, or fog hiding what is actually there.
    ///
    /// The rig is built once and reused for every frame of a capture. Rebuilding it per frame - which
    /// is what running the equivalent script through the code executor does - costs far more than the
    /// render itself.
    /// </summary>
    public sealed class DiagnosticRig : IDisposable
    {
        private readonly GameObject _root;
        private readonly RenderTexture _previousActive;
        private readonly AmbientMode _previousAmbientMode;
        private readonly Color _previousAmbientLight;
        private readonly float _previousAmbientIntensity;
        private readonly bool _previousFog;

        public Camera Camera { get; }

        private DiagnosticRig(GameObject root, Camera camera)
        {
            _root = root;
            Camera = camera;
            _previousActive = RenderTexture.active;
            _previousAmbientMode = RenderSettings.ambientMode;
            _previousAmbientLight = RenderSettings.ambientLight;
            _previousAmbientIntensity = RenderSettings.ambientIntensity;
            _previousFog = RenderSettings.fog;
        }

        /// <summary>
        /// Builds the rig framing either the given subject or every visible renderer in the scene.
        /// Returns null and fills <paramref name="error"/> when the scene has nothing to frame.
        /// </summary>
        public static DiagnosticRig Create(
            string subjectPath,
            int width,
            int height,
            List<string> warnings,
            out string error)
        {
            error = null;

            var renderers = new List<Renderer>();
            if (!string.IsNullOrEmpty(subjectPath))
            {
                var subject = GameObject.Find(subjectPath);
                if (subject == null)
                {
                    warnings.Add("subject not found; diagnostic capture uses all visible renderers");
                }
                else
                {
                    renderers.AddRange(subject.GetComponentsInChildren<Renderer>());
                }
            }

            if (renderers.Count == 0)
            {
                renderers.AddRange(UnityEngine.Object.FindObjectsByType<Renderer>());
            }

            if (renderers.Count == 0)
            {
                error = "No renderers found for diagnostic visual inspection.";
                return null;
            }

            var bounds = renderers[0].bounds;
            for (int i = 1; i < renderers.Count; i++)
            {
                bounds.Encapsulate(renderers[i].bounds);
            }

            var size = bounds.size;
            float radius = Mathf.Max(0.5f, size.magnitude * 0.5f);
            float aspect = (float)width / height;
            float orthographicSize = Mathf.Max(size.y * 0.55f, size.x / (2f * aspect)) * 1.15f;
            orthographicSize = Mathf.Max(orthographicSize, 0.75f);
            var center = bounds.center;
            float distance = Mathf.Max(radius * 4f, 4f);

            var root = new GameObject("Visora Diagnostic Capture");
            var cameraObject = new GameObject("Visora Diagnostic Camera");
            var keyLightObject = new GameObject("Visora Diagnostic Key Light");
            var fillLightObject = new GameObject("Visora Diagnostic Fill Light");
            cameraObject.transform.SetParent(root.transform);
            keyLightObject.transform.SetParent(root.transform);
            fillLightObject.transform.SetParent(root.transform);

            var camera = cameraObject.AddComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.74f, 0.76f, 0.78f, 1f);
            camera.cullingMask = ~0;
            camera.orthographic = true;
            camera.orthographicSize = orthographicSize;
            camera.nearClipPlane = 0.01f;
            camera.farClipPlane = 1000f;
            camera.allowHDR = false;
            camera.transform.position = center + new Vector3(0f, 0f, -distance);
            camera.transform.LookAt(center);

            ConfigureHighDefinitionCamera(cameraObject, warnings);

            var keyLight = keyLightObject.AddComponent<Light>();
            keyLight.type = LightType.Directional;
            keyLight.intensity = 2.1f;
            keyLight.transform.rotation = Quaternion.Euler(45f, -35f, 0f);

            var fillLight = fillLightObject.AddComponent<Light>();
            fillLight.type = LightType.Directional;
            fillLight.intensity = 0.9f;
            fillLight.transform.rotation = Quaternion.Euler(15f, 145f, 0f);

            var rig = new DiagnosticRig(root, camera);

            RenderSettings.ambientMode = AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.85f, 0.85f, 0.85f, 1f);
            RenderSettings.ambientIntensity = 1.8f;
            RenderSettings.fog = false;

            return rig;
        }

        /// <summary>
        /// Neutralises HDRP volume overrides on the diagnostic camera, so scene exposure and
        /// depth-of-field volumes cannot disguise the geometry being inspected. Uses reflection
        /// because the package must also compile in projects without HDRP installed.
        /// </summary>
        private static void ConfigureHighDefinitionCamera(GameObject cameraObject, List<string> warnings)
        {
            var hdCameraType = Type.GetType(
                "UnityEngine.Rendering.HighDefinition.HDAdditionalCameraData, Unity.RenderPipelines.HighDefinition.Runtime");
            if (hdCameraType == null) return;

            var hdCameraData = cameraObject.AddComponent(hdCameraType);

            var volumeLayerMaskField = hdCameraType.GetField("volumeLayerMask");
            if (volumeLayerMaskField != null)
            {
                volumeLayerMaskField.SetValue(hdCameraData, (LayerMask)0);
                warnings.Add(
                    "diagnostic_lit disables HDRP volumeLayerMask to avoid scene depth-of-field and exposure volumes");
            }

            var antialiasingField = hdCameraType.GetField("antialiasing");
            if (antialiasingField != null)
            {
                antialiasingField.SetValue(hdCameraData, Enum.ToObject(antialiasingField.FieldType, 0));
            }
        }

        public void Dispose()
        {
            RenderTexture.active = _previousActive;
            RenderSettings.ambientMode = _previousAmbientMode;
            RenderSettings.ambientLight = _previousAmbientLight;
            RenderSettings.ambientIntensity = _previousAmbientIntensity;
            RenderSettings.fog = _previousFog;

            if (_root != null)
            {
                UnityEngine.Object.DestroyImmediate(_root);
            }
        }
    }

    /// <summary>Native diagnostic_lit capture, single frame and real-time sequence.</summary>
    public static class DiagnosticCaptureService
    {
        public const string LightingWarning =
            "diagnostic_lit uses temporary camera, neutral background, temporary lighting, and disabled fog; " +
            "do not treat it as final game lighting";

        public static CameraRenderResult Capture(string subjectPath, int width, int height)
        {
            var result = new CameraRenderResult
            {
                width = width,
                height = height,
                format = "PNG",
                cameraName = "Visora Diagnostic Camera"
            };

            if (width <= 0 || height <= 0)
            {
                result.success = false;
                result.error = "width and height must be positive.";
                return result;
            }

            var rig = DiagnosticRig.Create(subjectPath, width, height, result.warnings, out string error);
            if (rig == null)
            {
                result.success = false;
                result.error = error;
                return result;
            }

            try
            {
                var render = CameraRenderingService.RenderCamera(rig.Camera, width, height, "PNG");
                render.warnings.AddRange(result.warnings);
                render.warnings.Add(LightingWarning);
                render.cameraName = "Visora Diagnostic Camera";
                return render;
            }
            finally
            {
                rig.Dispose();
            }
        }

        /// <summary>
        /// Records a diagnostic_lit sequence across real editor time, building the rig once.
        /// Must be driven by MainThreadDispatcher.EnqueueSteppedAsync.
        /// </summary>
        public static IEnumerator CaptureSequenceRoutine(  // NOSONAR - linear capture stages read better inline
            string subjectPath,
            int width,
            int height,
            int frameCount,
            float frameIntervalSeconds,
            CameraSequenceResult result)
        {
            result.cameraName = "Visora Diagnostic Camera";
            result.width = width;
            result.height = height;
            result.requestedFrameCount = frameCount;
            result.requestedFrameIntervalSeconds = frameIntervalSeconds;
            result.requestedFps = frameIntervalSeconds > 0f ? 1f / frameIntervalSeconds : 0f;
            result.timingSource = "native_realtime";

            if (width <= 0 || height <= 0)
            {
                result.success = false;
                result.error = "width and height must be positive.";
                yield break;
            }

            if (frameCount <= 0)
            {
                result.success = false;
                result.error = "frameCount must be at least 1.";
                yield break;
            }

            if (frameCount > CameraRenderingService.MaxSequenceFrames)
            {
                result.warnings.Add($"frameCount {frameCount} exceeds the {CameraRenderingService.MaxSequenceFrames} frame capture bound and was clamped.");
                frameCount = CameraRenderingService.MaxSequenceFrames;
            }

            if (frameIntervalSeconds < 0f)
            {
                result.warnings.Add("Negative frameIntervalSeconds was clamped to 0 (capture as fast as the editor allows).");
                frameIntervalSeconds = 0f;
            }

            var rig = DiagnosticRig.Create(subjectPath, width, height, result.warnings, out string error);
            if (rig == null)
            {
                result.success = false;
                result.error = error;
                yield break;
            }

            // Reported once for the whole sequence: repeating it per frame buries the frames it
            // describes under identical text.
            result.warnings.Add(LightingWarning);

            if (!EditorApplication.isPlaying)
            {
                result.warnings.Add(
                    "Editor is not in Play Mode: game time does not advance, so recorded frames may be identical.");
            }

            double start = EditorApplication.timeSinceStartup;

            for (int i = 0; i < frameCount; i++)
            {
                double targetTime = start + (i * frameIntervalSeconds);
                while (EditorApplication.timeSinceStartup < targetTime)
                {
                    yield return null;
                }

                var render = CameraRenderingService.RenderCamera(rig.Camera, width, height, "PNG");
                double now = EditorApplication.timeSinceStartup;

                if (!render.success)
                {
                    result.warnings.Add($"Frame {i} capture failed: {render.error}");
                }
                else
                {
                    result.frames.Add(new SequenceFrameData
                    {
                        frameIndex = i,
                        timestamp = (float)(now - start),
                        imageBase64 = render.imageBase64
                    });
                }

                yield return null;
            }

            rig.Dispose();

            result.frameCount = result.frames.Count;
            result.success = result.frames.Count > 0;

            if (!result.success && string.IsNullOrEmpty(result.error))
            {
                result.error = "No frames were captured during the diagnostic sequence.";
            }

            if (result.frames.Count >= 2)
            {
                result.totalDuration = result.frames[result.frames.Count - 1].timestamp - result.frames[0].timestamp;
                if (result.totalDuration > 0f)
                {
                    result.actualFps = (result.frames.Count - 1) / result.totalDuration;
                }
            }

            if (result.requestedFps > 0f && result.actualFps > 0f && result.actualFps < result.requestedFps * 0.9f)
            {
                result.warnings.Add(
                    $"Capture kept up at only {result.actualFps:F1} fps of the requested {result.requestedFps:F1} fps; " +
                    "timestamps reflect the real capture times.");
            }
        }
    }
}
