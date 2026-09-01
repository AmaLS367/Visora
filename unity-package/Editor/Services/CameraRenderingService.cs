using System;
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
        public int frameCount;
        public float totalDuration;
        public List<SequenceFrameData> frames = new List<SequenceFrameData>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// High-performance camera rendering service that directly blits camera output to RenderTextures.
    /// </summary>
    public static class CameraRenderingService
    {
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
            var result = new CameraRenderResult
            {
                width = width,
                height = height,
                format = format.ToUpperInvariant(),
                cameraName = cameraName
            };

            var cam = FindCamera(cameraName);
            if (cam == null)
            {
                result.success = false;
                result.error = $"No camera named '{cameraName}' was found in the active scene.";
                return result;
            }

            result.cameraName = cam.name;
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

        public static CameraSequenceResult CaptureSequence(string cameraName, int width = 1280, int height = 720, int frameCount = 10, float frameIntervalSeconds = 0.1f)
        {
            var result = new CameraSequenceResult
            {
                cameraName = cameraName,
                frameCount = frameCount,
                totalDuration = frameCount * frameIntervalSeconds
            };

            var cam = FindCamera(cameraName);
            if (cam == null)
            {
                result.success = false;
                result.error = $"No camera named '{cameraName}' was found for sequence capture.";
                return result;
            }

            result.cameraName = cam.name;

            for (int i = 0; i < frameCount; i++)
            {
                var render = RenderCamera(cameraName, width, height, "PNG");
                if (!render.success)
                {
                    result.warnings.Add($"Frame {i} capture failed: {render.error}");
                    continue;
                }

                result.frames.Add(new SequenceFrameData
                {
                    frameIndex = i,
                    timestamp = i * frameIntervalSeconds,
                    imageBase64 = render.imageBase64
                });
            }

            result.success = result.frames.Count > 0;
            return result;
        }
    }
}
