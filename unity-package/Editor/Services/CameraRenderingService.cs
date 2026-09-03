using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;

namespace Visora.Editor.Services
{
    [Serializable]
    public class CameraRenderResult
    {
        public bool success;
        public string error;
        public string imageBase64;
        public string format;
        public int width;
        public int height;
        public string cameraName;
        public float fov;
        public float nearClip;
        public float farClip;
        public float[] cameraPosition;
        public float[] cameraRotationEuler;
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class SequenceFrameData
    {
        public int frameIndex;
        public float timestamp;
        public string imageBase64;
    }

    [Serializable]
    public class CameraSequenceResult
    {
        public bool success;
        public string error;
        public string cameraName;
        public int width;
        public int height;
        public int requestedFrameCount;
        public int frameCount;
        public float requestedFps;
        public float actualFps;
        public float requestedFrameIntervalSeconds;
        public float totalDuration;
        public string timingSource = "native_realtime";
        public List<SequenceFrameData> frames = new List<SequenceFrameData>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// High-performance camera rendering service that directly blits camera output to RenderTextures.
    /// </summary>
    public static class CameraRenderingService
    {
        /// <summary>
        /// Hard upper bound on frames buffered in a single sequence capture. Every frame is held in
        /// memory as a base64 PNG until the whole sequence is serialized, so this bounds the response
        /// size and the editor-side allocation, independently of the caller's duration and fps.
        /// </summary>
        public const int MaxSequenceFrames = 240;

        public static Camera FindCamera(string cameraName)
        {
            if (string.IsNullOrEmpty(cameraName) || cameraName.Equals("Main Camera", StringComparison.OrdinalIgnoreCase) || cameraName.Equals("MainCamera", StringComparison.OrdinalIgnoreCase))
            {
                if (Camera.main != null) return Camera.main;
            }

            var cameras = UnityEngine.Object.FindObjectsOfType<Camera>();
            foreach (var cam in cameras)
            {
                if (cam.name.Equals(cameraName, StringComparison.OrdinalIgnoreCase))
                    return cam;
            }

            // Fallback to SceneView camera if available
            if (cameraName.Equals("SceneView", StringComparison.OrdinalIgnoreCase) || cameraName.Equals("Scene View", StringComparison.OrdinalIgnoreCase))
            {
                var sceneView = SceneView.lastActiveSceneView;
                if (sceneView != null && sceneView.camera != null)
                {
                    return sceneView.camera;
                }
            }

            // Fallback to first available camera
            return cameras.Length > 0 ? cameras[0] : null;
        }

        public static CameraRenderResult RenderCamera(string cameraName, int width = 1920, int height = 1080, string format = "PNG")
        {
            var cam = FindCamera(cameraName);
            if (cam == null)
            {
                return new CameraRenderResult
                {
                    success = false,
                    error = $"No camera named '{cameraName}' was found in the active scene.",
                    width = width,
                    height = height,
                    format = format.ToUpperInvariant(),
                    cameraName = cameraName
                };
            }

            return RenderCamera(cam, width, height, format);
        }

        /// <summary>
        /// Renders an already resolved camera. Sequence capture uses this overload so a multi-frame
        /// recording resolves the camera once instead of re-scanning the scene on every frame.
        /// </summary>
        public static CameraRenderResult RenderCamera(Camera cam, int width = 1920, int height = 1080, string format = "PNG")
        {
            var result = new CameraRenderResult
            {
                width = width,
                height = height,
                format = format.ToUpperInvariant(),
                cameraName = cam != null ? cam.name : null
            };

            if (cam == null)
            {
                result.success = false;
                result.error = "Camera reference is null or was destroyed before rendering.";
                return result;
            }

            result.fov = cam.fieldOfView;
            result.nearClip = cam.nearClipPlane;
            result.farClip = cam.farClipPlane;
            var pos = cam.transform.position;
            result.cameraPosition = new float[] { pos.x, pos.y, pos.z };
            var rot = cam.transform.rotation.eulerAngles;
            result.cameraRotationEuler = new float[] { rot.x, rot.y, rot.z };

            RenderTexture rt = null;
            Texture2D tex = null;
            var prevTarget = cam.targetTexture;
            var prevActive = RenderTexture.active;

            try
            {
                rt = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
                cam.targetTexture = rt;
                cam.Render();

                RenderTexture.active = rt;
                tex = new Texture2D(width, height, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                tex.Apply();

                byte[] bytes;
                if (result.format == "JPG" || result.format == "JPEG")
                {
                    bytes = tex.EncodeToJPG(90);
                }
                else
                {
                    bytes = tex.EncodeToPNG();
                    result.format = "PNG";
                }

                result.imageBase64 = Convert.ToBase64String(bytes);
                result.success = true;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Camera rendering failed: {ex.Message}";
            }
            finally
            {
                cam.targetTexture = prevTarget;
                RenderTexture.active = prevActive;
                if (rt != null) RenderTexture.ReleaseTemporary(rt);
                if (tex != null) UnityEngine.Object.DestroyImmediate(tex);
            }

            return result;
        }

        /// <summary>
        /// Records a camera over real editor time, advancing one step per editor update tick and
        /// rendering a frame whenever the wall clock reaches the next frame slot.
        ///
        /// This must be driven by MainThreadDispatcher.EnqueueSteppedAsync. Rendering the whole
        /// sequence inside a single main-thread call - as this service originally did - returns N
        /// copies of one instant, because no editor update runs between the renders and neither game
        /// time nor animation state advances.
        ///
        /// Timestamps are measured, not assumed: each frame reports the real offset from capture
        /// start, and actualFps reports the rate actually achieved so callers can encode video at the
        /// true rate instead of the requested one.
        /// </summary>
        public static IEnumerator CaptureSequenceRoutine(
            string cameraName,
            int width,
            int height,
            int frameCount,
            float frameIntervalSeconds,
            CameraSequenceResult result)
        {
            result.cameraName = cameraName;
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

            if (frameCount > MaxSequenceFrames)
            {
                result.warnings.Add($"frameCount {frameCount} exceeds the {MaxSequenceFrames} frame capture bound and was clamped.");
                frameCount = MaxSequenceFrames;
            }

            if (frameIntervalSeconds < 0f)
            {
                result.warnings.Add("Negative frameIntervalSeconds was clamped to 0 (capture as fast as the editor allows).");
                frameIntervalSeconds = 0f;
            }

            var cam = FindCamera(cameraName);
            if (cam == null)
            {
                result.success = false;
                result.error = $"No camera named '{cameraName}' was found for sequence capture.";
                yield break;
            }

            result.cameraName = cam.name;

            if (!EditorApplication.isPlaying)
            {
                result.warnings.Add(
                    "Editor is not in Play Mode: game time does not advance, so recorded frames may be identical. " +
                    "Use the animation preview sequence endpoint to step an authored clip in Edit Mode.");
            }

            double start = EditorApplication.timeSinceStartup;

            for (int i = 0; i < frameCount; i++)
            {
                double targetTime = start + (i * frameIntervalSeconds);
                while (EditorApplication.timeSinceStartup < targetTime)
                {
                    yield return null;
                }

                if (cam == null)
                {
                    cam = FindCamera(result.cameraName);
                    if (cam == null)
                    {
                        result.warnings.Add($"Frame {i}: camera '{result.cameraName}' no longer exists; capture stopped early.");
                        break;
                    }
                }

                var render = RenderCamera(cam, width, height, "PNG");
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

                // Always hand a tick back to the editor so the game loop advances between frames,
                // even when frameIntervalSeconds is 0.
                yield return null;
            }

            result.frameCount = result.frames.Count;
            result.success = result.frames.Count > 0;

            if (!result.success && string.IsNullOrEmpty(result.error))
            {
                result.error = "No frames were captured during the sequence.";
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
