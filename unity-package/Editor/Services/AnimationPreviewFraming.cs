using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    /// <summary>
    /// Framing verdicts and the temporary camera an authored clip preview renders through.
    ///
    /// Framing is judged against bounds unioned across samples of the clip, never the rest pose: a
    /// character standing in frame can leave it mid-jump, and a rest-pose verdict would call that
    /// preview fine. Any camera this creates is owned by the caller's finally block, so it cannot
    /// outlive the request that made it.
    /// </summary>
    public static class AnimationPreviewFraming
    {
        public const string StatusVisible = "visible";
        public const string StatusClipped = "clipped";
        public const string StatusOffScreen = "off_screen";
        public const string StatusBehindCamera = "behind_camera";
        public const string StatusNoRenderers = "no_renderers";
        public const string StatusCameraMissing = "camera_missing";

        /// <summary>Lower bound on bounds samples; a handful of poses steps straight over a fast kick.</summary>
        public const int MinBoundsSamples = 12;

        /// <summary>Upper bound, so a 240 frame capture does not pay for a second full pass over the clip.</summary>
        public const int MaxBoundsSamples = 48;

        public static int ResolveBoundsSampleCount(int frameCount)
        {
            return Mathf.Clamp(frameCount, 1, MaxBoundsSamples);
        }

        /// <summary>
        /// Unions renderer bounds across evenly spaced samples of the clip inside the open animation mode session.
        ///
        /// SkinnedMeshRenderer AABBs are not recomputed in Edit Mode while the mesh is considered off
        /// screen, so updateWhenOffscreen is forced on for the pass. Its restore closes here, before
        /// capture begins, so no later render or encode failure can leak the override.
        /// </summary>
        public static bool TryComputeClipBounds(
            GameObject target,
            AnimationClip clip,
            float startTime,
            float endTime,
            int sampleCount,
            List<string> warnings,
            out Bounds bounds)
        {
            bounds = new Bounds(target.transform.position, Vector3.zero);

            var renderers = target.GetComponentsInChildren<Renderer>(true);
            if (renderers.Length == 0)
            {
                return false;
            }

            var skinned = target.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            var previousUpdateWhenOffscreen = new bool[skinned.Length];
            for (int i = 0; i < skinned.Length; i++)
            {
                previousUpdateWhenOffscreen[i] = skinned[i].updateWhenOffscreen;
                skinned[i].updateWhenOffscreen = true;
            }

            bool initialized = false;
            try
            {
                int samples = Mathf.Max(1, sampleCount);
                float step = samples > 1 ? (endTime - startTime) / (samples - 1) : 0f;

                for (int sample = 0; sample < samples; sample++)
                {
                    float sampleTime = Mathf.Min(startTime + (step * sample), endTime);
                    try
                    {
                        AnimationMode.BeginSampling();
                        AnimationMode.SampleAnimationClip(target, clip, sampleTime);
                        AnimationMode.EndSampling();
                    }
                    catch (Exception ex)
                    {
                        warnings.Add($"Framing sample at {sampleTime:F3}s failed: {ex.Message}");
                        continue;
                    }

                    foreach (var renderer in renderers)
                    {
                        if (renderer == null || !renderer.enabled || !renderer.gameObject.activeInHierarchy) continue;
                        if (!initialized)
                        {
                            bounds = renderer.bounds;
                            initialized = true;
                        }
                        else
                        {
                            bounds.Encapsulate(renderer.bounds);
                        }
                    }
                }
            }
            finally
            {
                for (int i = 0; i < skinned.Length; i++)
                {
                    if (skinned[i] != null)
                    {
                        skinned[i].updateWhenOffscreen = previousUpdateWhenOffscreen[i];
                    }
                }
            }

            return initialized;
        }

        /// <summary>
        /// Classifies how a camera frames the given bounds, using the vocabulary
        /// CameraDiagnosticsService already emits so both paths mean the same words.
        /// </summary>
        public static string EvaluateFraming(Camera camera, Bounds bounds)
        {
            if (camera == null) return StatusCameraMissing;

            var min = new Vector3(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity);
            var max = new Vector3(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);
            int visible = 0;
            int behind = 0;

            foreach (var corner in Corners(bounds))
            {
                var viewport = camera.WorldToViewportPoint(corner);
                min = Vector3.Min(min, viewport);
                max = Vector3.Max(max, viewport);
                if (viewport.z < 0f) behind++;
                if (viewport.z >= 0f && viewport.x >= 0f && viewport.x <= 1f && viewport.y >= 0f && viewport.y <= 1f)
                {
                    visible++;
                }
            }

            if (behind == 8) return StatusBehindCamera;
            if (visible == 0) return StatusOffScreen;
            if (min.x < 0f || min.y < 0f || max.x > 1f || max.y > 1f) return StatusClipped;
            return StatusVisible;
        }

        /// <summary>
        /// Builds a throwaway camera that keeps the requested camera's look but frames the subject.
        ///
        /// CopySerialized rather than copying fields by hand: hand-copying loses the near and far
        /// clip planes and every render pipeline additional-data setting. The source GameObject is
        /// not cloned, because that would drag its MonoBehaviours into the preview. HideAndDontSave
        /// keeps the object out of the scene, so creating it cannot mark the scene modified.
        /// </summary>
        public static GameObject CreatePreviewCamera(
            Camera source,
            Bounds bounds,
            int width,
            int height,
            out Camera previewCamera)
        {
            var previewRoot = new GameObject("Visora Preview Camera")
            {
                hideFlags = HideFlags.HideAndDontSave
            };

            previewCamera = previewRoot.AddComponent<Camera>();
            EditorUtility.CopySerialized(source, previewCamera);

            foreach (var component in source.GetComponents<Component>())
            {
                if (component == null || component is Camera) continue;
                if (!component.GetType().Name.EndsWith("AdditionalCameraData", StringComparison.Ordinal)) continue;

                var copy = previewRoot.GetComponent(component.GetType());
                if (copy == null)
                {
                    copy = previewRoot.AddComponent(component.GetType());
                }

                if (copy != null)
                {
                    EditorUtility.CopySerialized(component, copy);
                }
            }

            float radius = Mathf.Max(0.01f, bounds.extents.magnitude);
            float distance;
            float aspect = height > 0 ? (float)width / height : 1f;
            if (source.orthographic)
            {
                distance = Mathf.Max(radius * 2f, Vector3.Distance(source.transform.position, bounds.center));
                previewCamera.orthographicSize =
                    Mathf.Max(Mathf.Max(bounds.size.y * 0.55f, bounds.size.x / (2f * aspect)) * 1.15f, 0.1f);
            }
            else
            {
                float halfFov = Mathf.Deg2Rad * Mathf.Clamp(source.fieldOfView, 1f, 179f) * 0.5f;
                float effectiveHalfFov = aspect < 1f
                    ? Mathf.Atan(Mathf.Tan(halfFov) * aspect)
                    : halfFov;
                distance = radius / Mathf.Max(0.01f, Mathf.Sin(effectiveHalfFov));
            }

            // Along the source camera's own forward axis, so the author's angle survives the reframing.
            previewRoot.transform.rotation = source.transform.rotation;
            previewRoot.transform.position = bounds.center - (source.transform.forward * distance);

            previewCamera.nearClipPlane = Mathf.Min(previewCamera.nearClipPlane, Mathf.Max(0.01f, distance * 0.01f));
            previewCamera.farClipPlane = Mathf.Max(previewCamera.farClipPlane, (distance + radius) * 2f);

            return previewRoot;
        }

        private static IEnumerable<Vector3> Corners(Bounds bounds)
        {
            var min = bounds.min;
            var max = bounds.max;
            yield return new Vector3(min.x, min.y, min.z);
            yield return new Vector3(max.x, min.y, min.z);
            yield return new Vector3(min.x, max.y, min.z);
            yield return new Vector3(max.x, max.y, min.z);
            yield return new Vector3(min.x, min.y, max.z);
            yield return new Vector3(max.x, min.y, max.z);
            yield return new Vector3(min.x, max.y, max.z);
            yield return new Vector3(max.x, max.y, max.z);
        }
    }
}
