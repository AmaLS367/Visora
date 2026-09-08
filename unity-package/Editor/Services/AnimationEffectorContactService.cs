using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class EffectorContactBakeRequest
    {
        public string clipPath;
        public string targetObjectPath;
        public string effector; // "left_foot", "right_foot", "left_hand", "right_hand"
        public string targetType; // "world_point", "scene_object", "camera_viewport"
        public float[] targetPosition;
        public string sceneObjectPath;
        public string cameraName;
        public float[] viewportCoordinates;
        public float viewportDepth;
        public float[] timeRange; // [startTime, endTime]
        public float blendInSeconds;
        public float blendOutSeconds;
        public float[] poleVector;
        public float[] targetRotation;
        public string operationId;
    }

    [Serializable]
    public class EffectorContactBakeResult
    {
        public bool success = true;
        public string error;
        public string clipPath;
        public string effector;
        public string backupId;
        public int keyframesModifiedCount;
        public float maxEffectorDisplacement;
        public float residualError;
        public float activeDuration;
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Bakes generalized 3D effector contacts (world point, moving scene object, camera viewport)
    /// into an AnimationClip with smooth cubic Hermite lead-in and lead-out ease curves.
    /// </summary>
    public static class AnimationEffectorContactService
    {
        public static EffectorContactBakeResult BakeContact(EffectorContactBakeRequest request)
        {
            var result = new EffectorContactBakeResult
            {
                clipPath = request?.clipPath,
                effector = request?.effector
            };

            if (EditorApplication.isPlaying)
            {
                result.success = false;
                result.error = "Bake effector contact requires Edit Mode; exit Play Mode before running.";
                return result;
            }

            if (request == null)
            {
                result.success = false;
                result.error = "Request cannot be null.";
                return result;
            }

            var rootGo = GameObject.Find(request.targetObjectPath);
            if (rootGo == null)
            {
                result.success = false;
                result.error = $"Target GameObject '{request.targetObjectPath}' not found in scene.";
                return result;
            }

            var clip = AnimationPreviewService.ResolveClip(request.clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip '{request.clipPath}' not found.";
                return result;
            }

            if (!InverseKinematicsService.ResolveLimbTransforms(
                    rootGo,
                    request.effector,
                    null, null, null,
                    out var rootBone,
                    out var midBone,
                    out var endBone,
                    out var blocker))
            {
                result.success = false;
                result.error = blocker ?? $"Could not resolve limb transforms for effector '{request.effector}'.";
                return result;
            }

            // Determine target position callback
            Vector3 staticWorldTarget = Vector3.zero;
            Transform targetSceneTransform = null;
            Camera targetCamera = null;

            string targetType = request.targetType?.ToLowerInvariant() ?? "world_point";
            if (targetType == "world_point")
            {
                if (request.targetPosition != null && request.targetPosition.Length >= 3)
                {
                    staticWorldTarget = new Vector3(request.targetPosition[0], request.targetPosition[1], request.targetPosition[2]);
                }
                else
                {
                    result.success = false;
                    result.error = "targetType 'world_point' requires targetPosition [x, y, z].";
                    return result;
                }
            }
            else if (targetType == "scene_object")
            {
                var obj = GameObject.Find(request.sceneObjectPath);
                if (obj == null)
                {
                    result.success = false;
                    result.error = $"Scene target object '{request.sceneObjectPath}' not found.";
                    return result;
                }
                targetSceneTransform = obj.transform;
            }
            else if (targetType == "camera_viewport")
            {
                targetCamera = CameraRenderingService.FindCamera(request.cameraName);
                if (targetCamera == null)
                {
                    result.success = false;
                    result.error = $"Camera '{request.cameraName}' not found.";
                    return result;
                }
            }
            else
            {
                result.success = false;
                result.error = $"Unsupported targetType '{request.targetType}'.";
                return result;
            }

            float tStart = request.timeRange != null && request.timeRange.Length >= 1 ? request.timeRange[0] : 0f;
            float tEnd = request.timeRange != null && request.timeRange.Length >= 2 ? request.timeRange[1] : clip.length;
            float blendIn = Mathf.Max(0.001f, request.blendInSeconds);
            float blendOut = Mathf.Max(0.001f, request.blendOutSeconds);

            float windowStart = Mathf.Max(0f, tStart - blendIn);
            float windowEnd = Mathf.Min(clip.length, tEnd + blendOut);

            if (windowStart >= windowEnd)
            {
                result.success = false;
                result.error = $"Invalid contact time range [{tStart}, {tEnd}] for clip length {clip.length:F2}s.";
                return result;
            }

            result.activeDuration = windowEnd - windowStart;

            // Pre-mutation backup
            try
            {
                result.backupId = AnimationBackupService.WriteBackup(clip, request.clipPath, "bake_effector_contact");
            }
            catch (Exception ex)
            {
                result.warnings.Add($"Pre-mutation backup warning: {ex.Message}");
            }

            Undo.RegisterCompleteObjectUndo(clip, "Visora Bake Effector Contact");

            // Snapshot rest pose of rootGo transforms
            var allTransforms = rootGo.GetComponentsInChildren<Transform>(true);
            var restPos = new Vector3[allTransforms.Length];
            var restRot = new Quaternion[allTransforms.Length];
            for (int i = 0; i < allTransforms.Length; i++)
            {
                restPos[i] = allTransforms[i].localPosition;
                restRot[i] = allTransforms[i].localRotation;
            }

            Vector3? poleVec = null;
            if (request.poleVector != null && request.poleVector.Length >= 3)
            {
                poleVec = new Vector3(request.poleVector[0], request.poleVector[1], request.poleVector[2]);
            }

            Quaternion? targetRot = null;
            if (request.targetRotation != null && request.targetRotation.Length >= 4)
            {
                targetRot = new Quaternion(request.targetRotation[0], request.targetRotation[1], request.targetRotation[2], request.targetRotation[3]);
            }

            float fps = clip.frameRate > 0f ? clip.frameRate : 60f;
            float dt = 1f / fps;
            int totalFrames = Mathf.Max(2, Mathf.RoundToInt(clip.length * fps));

            var rootRotCurveX = new AnimationCurve();
            var rootRotCurveY = new AnimationCurve();
            var rootRotCurveZ = new AnimationCurve();
            var rootRotCurveW = new AnimationCurve();

            var midRotCurveX = new AnimationCurve();
            var midRotCurveY = new AnimationCurve();
            var midRotCurveZ = new AnimationCurve();
            var midRotCurveW = new AnimationCurve();

            var endRotCurveX = new AnimationCurve();
            var endRotCurveY = new AnimationCurve();
            var endRotCurveZ = new AnimationCurve();
            var endRotCurveW = new AnimationCurve();

            float maxDisplacement = 0f;
            float maxResidual = 0f;
            int modifiedCount = 0;

            try
            {
                for (int f = 0; f < totalFrames; f++)
                {
                    float t = Mathf.Clamp(f * dt, 0f, clip.length);

                    AnimationMode.BeginSampling();
                    AnimationMode.SampleAnimationClip(rootGo, clip, t);
                    AnimationMode.EndSampling();

                    Vector3 originalEndPos = endBone.position;

                    // Calculate Hermite blend weight
                    float w = 0f;
                    if (t >= tStart && t <= tEnd)
                    {
                        w = 1f;
                    }
                    else if (t >= windowStart && t < tStart)
                    {
                        float u = (t - windowStart) / blendIn;
                        w = (3f * u * u) - (2f * u * u * u);
                    }
                    else if (t > tEnd && t <= windowEnd)
                    {
                        float u = (t - tEnd) / blendOut;
                        w = 1f - ((3f * u * u) - (2f * u * u * u));
                    }

                    if (w > 0.0001f)
                    {
                        // Determine target world position
                        Vector3 currentTargetPos = staticWorldTarget;
                        if (targetType == "scene_object" && targetSceneTransform != null)
                        {
                            currentTargetPos = targetSceneTransform.position;
                        }
                        else if (targetType == "camera_viewport" && targetCamera != null)
                        {
                            float u = request.viewportCoordinates != null && request.viewportCoordinates.Length >= 1 ? request.viewportCoordinates[0] : 0.5f;
                            float v = request.viewportCoordinates != null && request.viewportCoordinates.Length >= 2 ? request.viewportCoordinates[1] : 0.5f;
                            float depth = request.viewportDepth > 0.01f ? request.viewportDepth : 0.5f;
                            currentTargetPos = targetCamera.ViewportToWorldPoint(new Vector3(u, v, depth));
                        }

                        InverseKinematicsService.SolveTwoBoneIKInternal(
                            rootBone,
                            midBone,
                            endBone,
                            currentTargetPos,
                            targetRot,
                            poleVec,
                            w,
                            out bool clamped,
                            out float reachDistance,
                            out float actualDistance,
                            out float posResidual,
                            out float rotResidualDeg);

                        float displacement = Vector3.Distance(originalEndPos, endBone.position);
                        if (displacement > maxDisplacement) maxDisplacement = displacement;
                        if (posResidual > maxResidual) maxResidual = posResidual;
                    }

                    // Capture bone local rotations
                    var rRot = rootBone.localRotation;
                    var mRot = midBone.localRotation;
                    var eRot = endBone.localRotation;

                    rootRotCurveX.AddKey(t, rRot.x);
                    rootRotCurveY.AddKey(t, rRot.y);
                    rootRotCurveZ.AddKey(t, rRot.z);
                    rootRotCurveW.AddKey(t, rRot.w);

                    midRotCurveX.AddKey(t, mRot.x);
                    midRotCurveY.AddKey(t, mRot.y);
                    midRotCurveZ.AddKey(t, mRot.z);
                    midRotCurveW.AddKey(t, mRot.w);

                    if (targetRot.HasValue)
                    {
                        endRotCurveX.AddKey(t, eRot.x);
                        endRotCurveY.AddKey(t, eRot.y);
                        endRotCurveZ.AddKey(t, eRot.z);
                        endRotCurveW.AddKey(t, eRot.w);
                    }

                    modifiedCount += targetRot.HasValue ? 12 : 8;
                }

                // Write curves into clip
                string rootRelPath = AnimationUtility.CalculateTransformPath(rootBone, rootGo.transform);
                string midRelPath = AnimationUtility.CalculateTransformPath(midBone, rootGo.transform);

                SetCurves(clip, rootRelPath, rootRotCurveX, rootRotCurveY, rootRotCurveZ, rootRotCurveW);
                SetCurves(clip, midRelPath, midRotCurveX, midRotCurveY, midRotCurveZ, midRotCurveW);

                if (targetRot.HasValue)
                {
                    string endRelPath = AnimationUtility.CalculateTransformPath(endBone, rootGo.transform);
                    SetCurves(clip, endRelPath, endRotCurveX, endRotCurveY, endRotCurveZ, endRotCurveW);
                }

                clip.EnsureQuaternionContinuity();
                EditorUtility.SetDirty(clip);
                AssetDatabase.SaveAssets();

                result.success = true;
                result.keyframesModifiedCount = modifiedCount;
                result.maxEffectorDisplacement = maxDisplacement;
                result.residualError = maxResidual;
                return result;
            }
            finally
            {
                // Restore rest pose
                for (int i = 0; i < allTransforms.Length; i++)
                {
                    if (allTransforms[i] != null)
                    {
                        allTransforms[i].localPosition = restPos[i];
                        allTransforms[i].localRotation = restRot[i];
                    }
                }
            }
        }

        private static void SetCurves(AnimationClip clip, string path, AnimationCurve x, AnimationCurve y, AnimationCurve z, AnimationCurve w)
        {
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.x", x);
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.y", y);
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.z", z);
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.w", w);
        }
    }
}
