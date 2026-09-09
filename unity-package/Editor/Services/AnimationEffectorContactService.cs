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
            return BakeContactInternal(
                request, null, null, manageUndo: true, saveAssets: true, restoreOnFailure: true);
        }

        internal static EffectorContactBakeResult BakePreparedContact(
            EffectorContactBakeRequest request,
            string preparedBackupId,
            AnimationClip targetCameraClip)
        {
            return BakeContactInternal(
                request, preparedBackupId, targetCameraClip,
                manageUndo: false, saveAssets: false, restoreOnFailure: false);
        }

        private static EffectorContactBakeResult BakeContactInternal(
            EffectorContactBakeRequest request,
            string preparedBackupId,
            AnimationClip targetCameraClip,
            bool manageUndo,
            bool saveAssets,
            bool restoreOnFailure)
        {
            var result = new EffectorContactBakeResult
            {
                clipPath = request?.clipPath,
                effector = request?.effector
            };

            string editModeErr = AnimationBackupService.CheckEditMode();
            if (editModeErr != null)
            {
                result.success = false;
                result.error = editModeErr;
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

            string rotationConflict = FindEulerRotationConflict(clip, rootGo.transform, rootBone, midBone, endBone);
            if (rotationConflict != null)
            {
                result.success = false;
                result.error = rotationConflict;
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

            if (!string.IsNullOrEmpty(preparedBackupId))
            {
                result.backupId = preparedBackupId;
            }
            else
            {
                // A contact bake is not allowed to mutate an asset without a recoverable snapshot.
                try
                {
                    result.backupId = AnimationBackupService.WriteBackup(clip, request.clipPath, "bake_effector_contact");
                }
                catch (Exception ex)
                {
                    result.success = false;
                    result.error = $"Pre-mutation backup failed; contact bake aborted: {ex.Message}";
                    return result;
                }
            }

            if (manageUndo) Undo.RegisterCompleteObjectUndo(clip, "Visora Bake Effector Contact");

            // Snapshot rest pose of rootGo transforms
            var allTransforms = rootGo.GetComponentsInChildren<Transform>(true);
            var restPos = new Vector3[allTransforms.Length];
            var restRot = new Quaternion[allTransforms.Length];
            for (int i = 0; i < allTransforms.Length; i++)
            {
                restPos[i] = allTransforms[i].localPosition;
                restRot[i] = allTransforms[i].localRotation;
            }
            Vector3 cameraRestPosition = targetCamera != null ? targetCamera.transform.localPosition : Vector3.zero;
            Quaternion cameraRestRotation = targetCamera != null ? targetCamera.transform.localRotation : Quaternion.identity;

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

            // Only frames inside the blended contact window are re-authored; keys elsewhere on the
            // m_LocalRotation channels are preserved (AnimationCurveWriter upserts, never replaces).
            var allTimes = AnimationSampling.BuildFrameTimes(clip.length, fps);
            var exactTimes = new SortedSet<float>
            {
                windowStart,
                Mathf.Clamp(tStart, windowStart, windowEnd),
                Mathf.Clamp(tEnd, windowStart, windowEnd),
                windowEnd,
            };
            foreach (float t in allTimes)
            {
                if (t >= windowStart - 1e-4f && t <= windowEnd + 1e-4f) exactTimes.Add(t);
            }
            var windowTimes = new List<float>(exactTimes);
            if (windowTimes.Count < 2)
            {
                result.success = false;
                result.error = $"Contact window [{windowStart:F2}, {windowEnd:F2}]s is too short to sample at {fps:F0} fps.";
                return result;
            }

            var rootSamples = new List<(float, Quaternion)>(windowTimes.Count);
            var midSamples = new List<(float, Quaternion)>(windowTimes.Count);
            var endSamples = new List<(float, Quaternion)>(windowTimes.Count);

            float maxDisplacement = 0f;
            float maxResidual = 0f;
            int modifiedCount = 0;

            try
            {
                AnimationSampling.SampleClip(rootGo, clip, windowTimes, i =>
                {
                    float t = windowTimes[i];
                    Vector3 originalEndPos = endBone.position;

                    // Cubic Hermite (smoothstep) blend weight across the lead-in / lead-out.
                    float w = 0f;
                    if (t >= tStart && t <= tEnd)
                    {
                        w = 1f;
                    }
                    else if (t >= windowStart && t < tStart)
                    {
                        float u = Mathf.Clamp01((t - windowStart) / blendIn);
                        w = (3f * u * u) - (2f * u * u * u);
                    }
                    else if (t > tEnd && t <= windowEnd)
                    {
                        float u = Mathf.Clamp01((t - tEnd) / blendOut);
                        w = 1f - ((3f * u * u) - (2f * u * u * u));
                    }

                    if (w > 0.0001f)
                    {
                        Vector3 currentTargetPos = staticWorldTarget;
                        if (targetType == "scene_object" && targetSceneTransform != null)
                        {
                            currentTargetPos = targetSceneTransform.position;
                        }
                        else if (targetType == "camera_viewport" && targetCamera != null)
                        {
                            if (targetCameraClip != null)
                            {
                                AnimationMode.SampleAnimationClip(targetCamera.gameObject, targetCameraClip, t);
                            }
                            float u = request.viewportCoordinates != null && request.viewportCoordinates.Length >= 1 ? request.viewportCoordinates[0] : 0.5f;
                            float v = request.viewportCoordinates != null && request.viewportCoordinates.Length >= 2 ? request.viewportCoordinates[1] : 0.5f;
                            float depth = request.viewportDepth > 0.01f ? request.viewportDepth : 0.5f;
                            currentTargetPos = targetCamera.ViewportToWorldPoint(new Vector3(u, v, depth));
                        }

                        InverseKinematicsService.SolveTwoBoneIKInternal(
                            rootBone, midBone, endBone, currentTargetPos, targetRot, poleVec, w,
                            out _, out _, out _, out float posResidual, out _);

                        float displacement = Vector3.Distance(originalEndPos, endBone.position);
                        if (displacement > maxDisplacement) maxDisplacement = displacement;
                        // Contact residual describes the locked portion of the window. During the
                        // lead-in/out the solve is intentionally partial, so comparing that pose
                        // with the full target would report the blend itself as an IK error.
                        if (w >= 0.9999f && posResidual > maxResidual) maxResidual = posResidual;
                    }

                    rootSamples.Add((t, rootBone.localRotation));
                    midSamples.Add((t, midBone.localRotation));
                    if (targetRot.HasValue) endSamples.Add((t, endBone.localRotation));
                    modifiedCount += targetRot.HasValue ? 12 : 8;
                });

                AnimationCurveWriter.WriteQuaternionCurves(
                    clip, rootGo.transform, rootBone, rootSamples, windowStart, windowEnd);
                AnimationCurveWriter.WriteQuaternionCurves(
                    clip, rootGo.transform, midBone, midSamples, windowStart, windowEnd);
                if (targetRot.HasValue)
                {
                    AnimationCurveWriter.WriteQuaternionCurves(
                        clip, rootGo.transform, endBone, endSamples, windowStart, windowEnd);
                }

                clip.EnsureQuaternionContinuity();
                EditorUtility.SetDirty(clip);
                if (saveAssets) AssetDatabase.SaveAssets();

                result.success = true;
                result.keyframesModifiedCount = modifiedCount;
                result.maxEffectorDisplacement = maxDisplacement;
                result.residualError = maxResidual;
                return result;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Effector contact bake failed: {ex.Message}";
                if (restoreOnFailure && !string.IsNullOrEmpty(result.backupId))
                {
                    try
                    {
                        AnimationBackupService.RestoreBackup(clip, request.clipPath, result.backupId, null);
                        AssetDatabase.SaveAssets();
                        result.warnings.Add("Clip restored from pre-bake backup after the failure.");
                    }
                    catch (Exception restoreEx)
                    {
                        result.warnings.Add($"Rollback also failed: {restoreEx.Message}");
                    }
                }
                return result;
            }
            finally
            {
                // Restore rest pose (covers the case where animation mode was already active on entry).
                for (int i = 0; i < allTransforms.Length; i++)
                {
                    if (allTransforms[i] != null)
                    {
                        allTransforms[i].localPosition = restPos[i];
                        allTransforms[i].localRotation = restRot[i];
                    }
                }
                if (targetCamera != null)
                {
                    targetCamera.transform.localPosition = cameraRestPosition;
                    targetCamera.transform.localRotation = cameraRestRotation;
                }
            }
        }

        private static string FindEulerRotationConflict(
            AnimationClip clip,
            Transform animationRoot,
            params Transform[] bones)
        {
            var editedPaths = new HashSet<string>(StringComparer.Ordinal);
            foreach (var bone in bones)
            {
                if (bone != null)
                {
                    editedPaths.Add(AnimationUtility.CalculateTransformPath(bone, animationRoot));
                }
            }

            foreach (var binding in AnimationUtility.GetCurveBindings(clip))
            {
                if (editedPaths.Contains(binding.path)
                    && binding.propertyName.Contains("Euler", StringComparison.OrdinalIgnoreCase))
                {
                    return $"Euler rotation curve '{binding.propertyName}' on '{binding.path}' conflicts with quaternion contact baking.";
                }
            }
            return null;
        }
    }
}
