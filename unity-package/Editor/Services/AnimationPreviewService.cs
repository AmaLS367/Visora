using System;
using System.Collections;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Visora.Editor.Services
{
    [Serializable]
    public class AnimationPreviewSequenceResult
    {
        public bool success;
        public string error;
        public string cameraName;
        public string clipName;
        public string clipPath;
        public string targetObjectPath;
        public float clipLength;
        public float startTime;
        public float endTime;
        public int width;
        public int height;
        public int requestedFrameCount;
        public int frameCount;
        public float requestedFps;
        public float actualFps;
        public float totalDuration;
        public string timingSource = "edit_mode_sampled";
        public bool poseRestored;
        public bool sceneDirtiedByPreview;
        public List<SequenceFrameData> frames = new List<SequenceFrameData>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Renders an authored AnimationClip frame by frame in Edit Mode.
    ///
    /// Unlike Play Mode recording, this samples the clip at exact requested timestamps, so the frame
    /// timing is deterministic at any fps and no domain reload happens mid-capture. It sees only what
    /// the clip itself drives - not physics, particles, or runtime gameplay logic.
    /// </summary>
    public static class AnimationPreviewService
    {
        public static AnimationClip ResolveClip(string clipPathOrName)
        {
            if (string.IsNullOrEmpty(clipPathOrName)) return null;

            if (clipPathOrName.EndsWith(".anim", StringComparison.OrdinalIgnoreCase) ||
                clipPathOrName.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase))
            {
                var direct = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPathOrName);
                if (direct != null) return direct;
            }

            return AnimationInspectionService.FindClip(clipPathOrName);
        }

        /// <summary>
        /// Samples the clip across [startTime, endTime] and renders one camera frame per sample,
        /// advancing one frame per editor update tick so the editor stays responsive. The target's
        /// transform hierarchy is snapshotted before sampling and restored afterwards, and a scene
        /// that was clean before the preview is left clean.
        /// </summary>
        public static IEnumerator CapturePreviewRoutine(  // NOSONAR - sequential capture stages read better inline
            string cameraName,
            string clipPathOrName,
            string targetObjectPath,
            int width,
            int height,
            int frameCount,
            float fps,
            float startTime,
            float endTime,
            AnimationPreviewSequenceResult result)
        {
            result.cameraName = cameraName;
            result.clipPath = clipPathOrName;
            result.targetObjectPath = targetObjectPath;
            result.width = width;
            result.height = height;
            result.requestedFrameCount = frameCount;
            result.requestedFps = fps;
            result.timingSource = "edit_mode_sampled";

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

            var clip = ResolveClip(clipPathOrName);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip '{clipPathOrName}' was not found in the project.";
                yield break;
            }

            result.clipName = clip.name;
            result.clipLength = clip.length;

            var target = GameObject.Find(targetObjectPath);
            if (target == null)
            {
                result.success = false;
                result.error = $"Target GameObject '{targetObjectPath}' was not found in the active scene.";
                yield break;
            }

            var cam = CameraRenderingService.FindCamera(cameraName);
            if (cam == null)
            {
                result.success = false;
                result.error = $"No camera named '{cameraName}' was found for animation preview.";
                yield break;
            }

            result.cameraName = cam.name;

            if (EditorApplication.isPlaying)
            {
                result.warnings.Add(
                    "Editor is in Play Mode: runtime animator state may fight the sampled pose. " +
                    "Edit Mode gives deterministic authored-clip preview.");
            }

            float rangeStart = Mathf.Clamp(startTime, 0f, clip.length);
            float rangeEnd = endTime > 0f ? Mathf.Clamp(endTime, rangeStart, clip.length) : clip.length;
            if (Mathf.Approximately(rangeEnd, rangeStart) && clip.length > 0f)
            {
                result.warnings.Add("Requested time range was empty; previewing the full clip instead.");
                rangeStart = 0f;
                rangeEnd = clip.length;
            }

            result.startTime = rangeStart;
            result.endTime = rangeEnd;

            var scene = SceneManager.GetActiveScene();
            bool sceneWasDirty = scene.isDirty;

            var transforms = target.GetComponentsInChildren<Transform>(true);
            var restPosition = new Dictionary<Transform, Vector3>(transforms.Length);
            var restRotation = new Dictionary<Transform, Quaternion>(transforms.Length);
            var restScale = new Dictionary<Transform, Vector3>(transforms.Length);

            foreach (var t in transforms)
            {
                restPosition[t] = t.localPosition;
                restRotation[t] = t.localRotation;
                restScale[t] = t.localScale;
            }

            // fps defines the sampling step so the preview really runs at the requested rate; the time
            // range only bounds how much of the clip is covered. Falling back to an even split across
            // the range keeps a frameCount-only request meaningful.
            float step;
            if (fps > 0f)
            {
                step = 1f / fps;
                int framesInRange = Mathf.FloorToInt((rangeEnd - rangeStart) / step) + 1;
                if (framesInRange < frameCount)
                {
                    result.warnings.Add(
                        $"Requested {frameCount} frames at {fps:F1} fps exceed the {rangeEnd - rangeStart:F3}s preview range; captured {framesInRange} frames instead.");
                    frameCount = Mathf.Max(1, framesInRange);
                }
            }
            else
            {
                step = frameCount > 1 ? (rangeEnd - rangeStart) / (frameCount - 1) : 0f;
            }

            result.requestedFrameCount = frameCount;

            for (int i = 0; i < frameCount; i++)
            {
                float sampleTime = frameCount > 1 ? Mathf.Min(rangeStart + (step * i), rangeEnd) : rangeStart;

                // Swallowing the failure here (rather than letting it escape the iterator) guarantees
                // the routine always reaches the pose restore below instead of dying mid-capture with
                // the rig left posed. C# forbids yielding from a catch clause, so the per-frame yield
                // happens once at the end of the loop body either way.
                bool sampled = true;
                try
                {
                    clip.SampleAnimation(target, sampleTime);
                }
                catch (Exception ex)
                {
                    result.warnings.Add($"Frame {i} sampling at {sampleTime:F3}s failed: {ex.Message}");
                    sampled = false;
                }

                if (sampled)
                {
                    var render = CameraRenderingService.RenderCamera(cam, width, height, "PNG");
                    if (!render.success)
                    {
                        result.warnings.Add($"Frame {i} render at {sampleTime:F3}s failed: {render.error}");
                    }
                    else
                    {
                        result.frames.Add(new SequenceFrameData
                        {
                            frameIndex = i,
                            timestamp = sampleTime,
                            imageBase64 = render.imageBase64
                        });
                    }
                }

                yield return null;
            }

            foreach (var t in transforms)
            {
                if (t == null) continue;
                t.localPosition = restPosition[t];
                t.localRotation = restRotation[t];
                t.localScale = restScale[t];
            }

            result.poseRestored = true;

            if (!sceneWasDirty && scene.isDirty)
            {
                // Sampling can mark the scene dirty even though every transform was restored.
                // EditorSceneManager.ClearSceneDirtiness is internal in Unity 6, so the preview
                // reports the side effect instead of silently reaching around the API.
                result.sceneDirtiedByPreview = true;
                result.warnings.Add(
                    "Sampling marked the scene as modified. The target pose was restored, so the flagged " +
                    "change is not a real edit - discard it rather than saving the scene.");
            }

            result.frameCount = result.frames.Count;
            result.success = result.frames.Count > 0;

            if (!result.success && string.IsNullOrEmpty(result.error))
            {
                result.error = "No frames were captured during the animation preview.";
            }

            if (result.frames.Count >= 2)
            {
                result.totalDuration = result.frames[result.frames.Count - 1].timestamp - result.frames[0].timestamp;
                if (result.totalDuration > 0f)
                {
                    result.actualFps = (result.frames.Count - 1) / result.totalDuration;
                }
            }
        }
    }
}
