using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class CameraSubjectContactRequest
    {
        public string characterPath;
        public string characterClipPath;
        public string cameraName;
        public string cameraClipPath;
        public string effector;
        public float impactTime;
        public float contactDuration;
        public float[] lensViewport;
        public float lensDistanceMeters;
        public float hitStopDuration;
        public float[] cameraRecoilImpulse;
    }

    [Serializable]
    public class CameraSubjectContactResult
    {
        public bool success = true;
        public string error;
        public string characterBackupId;
        public string cameraBackupId;
        public float[] impactWorldPosition;
        public float[] impactScreenResidualPixels;
        public float maxLimbReachRatio;
        public int keyframesModifiedCount;
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Authors character contact, hit-stop, and camera recoil as one multi-clip transaction.
    /// Every clip is resolved and backed up before the first curve is changed.
    /// </summary>
    public static class CameraSubjectActionService
    {
        public static CameraSubjectContactResult SolveCameraSubjectContact(CameraSubjectContactRequest request)
        {
            var result = new CameraSubjectContactResult();
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

            var characterGo = GameObject.Find(request.characterPath);
            if (characterGo == null)
            {
                result.success = false;
                result.error = $"Character GameObject '{request.characterPath}' not found.";
                return result;
            }
            var camera = CameraRenderingService.FindCamera(request.cameraName);
            if (camera == null)
            {
                result.success = false;
                result.error = $"Camera '{request.cameraName}' not found.";
                return result;
            }
            var charClip = AnimationPreviewService.ResolveClip(request.characterClipPath);
            if (charClip == null)
            {
                result.success = false;
                result.error = $"Character AnimationClip '{request.characterClipPath}' not found.";
                return result;
            }

            AnimationClip camClip = null;
            if (!string.IsNullOrEmpty(request.cameraClipPath))
            {
                camClip = AnimationPreviewService.ResolveClip(request.cameraClipPath);
                if (camClip == null)
                {
                    result.success = false;
                    result.error = $"Camera AnimationClip '{request.cameraClipPath}' not found.";
                    return result;
                }
            }

            try
            {
                result.characterBackupId = AnimationBackupService.WriteBackup(
                    charClip, request.characterClipPath, "camera_subject_character");
                if (camClip != null)
                {
                    result.cameraBackupId = AnimationBackupService.WriteBackup(
                        camClip, request.cameraClipPath, "camera_subject_camera");
                }
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Camera-subject pre-mutation backup failed; solve aborted: {ex.Message}";
                return result;
            }

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora Camera-Subject Contact Solve");
            Undo.RegisterCompleteObjectUndo(charClip, "Visora Camera-Subject Character Contact");
            if (camClip != null) Undo.RegisterCompleteObjectUndo(camClip, "Visora Camera Recoil");

            int totalKeysModified = 0;
            try
            {
                float u = request.lensViewport != null && request.lensViewport.Length >= 1
                    ? request.lensViewport[0] : 0.5f;
                float v = request.lensViewport != null && request.lensViewport.Length >= 2
                    ? request.lensViewport[1] : 0.5f;
                float depth = request.lensDistanceMeters > 0.05f ? request.lensDistanceMeters : 0.3f;

                Vector3 baseCamPos = camera.transform.localPosition;
                if (camClip != null)
                {
                    AnimationSampling.SampleClip(camera.gameObject, camClip, new[] { request.impactTime },
                        _ => baseCamPos = camera.transform.localPosition);
                    Vector3 recoil = request.cameraRecoilImpulse != null && request.cameraRecoilImpulse.Length >= 3
                        ? new Vector3(
                            request.cameraRecoilImpulse[0],
                            request.cameraRecoilImpulse[1],
                            request.cameraRecoilImpulse[2])
                        : new Vector3(0f, -0.15f, -0.4f);
                    Vector3 peakCamPos = baseCamPos + recoil;
                    float t0 = request.impactTime;
                    float tPeak = t0 + 0.04f;
                    float tHold = tPeak + (request.hitStopDuration > 0.01f ? request.hitStopDuration : 0.04f);
                    float tSettle = tHold + 0.2f;

                    totalKeysModified += RequireSuccess(AnimationAuthoringService.SetPreparedKeyframe(
                        request.cameraClipPath, "", "Transform", "m_LocalPosition", t0,
                        new[] { baseCamPos.x, baseCamPos.y, baseCamPos.z }, "smooth"), "camera recoil start");
                    totalKeysModified += RequireSuccess(AnimationAuthoringService.SetPreparedKeyframe(
                        request.cameraClipPath, "", "Transform", "m_LocalPosition", tPeak,
                        new[] { peakCamPos.x, peakCamPos.y, peakCamPos.z }, "smooth"), "camera recoil peak");
                    totalKeysModified += RequireSuccess(AnimationAuthoringService.SetPreparedKeyframe(
                        request.cameraClipPath, "", "Transform", "m_LocalPosition", tHold,
                        new[] { peakCamPos.x, peakCamPos.y, peakCamPos.z }, "smooth"), "camera recoil hold");
                    totalKeysModified += RequireSuccess(AnimationAuthoringService.SetPreparedKeyframe(
                        request.cameraClipPath, "", "Transform", "m_LocalPosition", tSettle,
                        new[] { baseCamPos.x, baseCamPos.y, baseCamPos.z }, "smooth"), "camera recoil settle");
                }

                float contactDur = Mathf.Max(0.05f, request.contactDuration);
                var bakeRes = AnimationEffectorContactService.BakePreparedContact(
                    new EffectorContactBakeRequest
                    {
                        clipPath = request.characterClipPath,
                        targetObjectPath = request.characterPath,
                        effector = request.effector,
                        targetType = "camera_viewport",
                        cameraName = request.cameraName,
                        viewportCoordinates = new[] { u, v },
                        viewportDepth = depth,
                        timeRange = new[] { request.impactTime, request.impactTime + contactDur },
                        blendInSeconds = 0.08f,
                        blendOutSeconds = 0.12f,
                    },
                    result.characterBackupId,
                    camClip);
                if (!bakeRes.success)
                {
                    throw new InvalidOperationException($"Character effector bake failed: {bakeRes.error}");
                }
                totalKeysModified += bakeRes.keyframesModifiedCount;
                result.warnings.AddRange(bakeRes.warnings);

                if (!InverseKinematicsService.ResolveLimbTransforms(
                        characterGo, request.effector, null, null, null,
                        out var rootBone, out var midBone, out var endBone, out var blocker))
                {
                    throw new InvalidOperationException(blocker ?? "Character limb could not be resolved after contact bake.");
                }

                if (request.hitStopDuration > 0.01f)
                {
                    string rootRel = AnimationUtility.CalculateTransformPath(rootBone, characterGo.transform);
                    string midRel = AnimationUtility.CalculateTransformPath(midBone, characterGo.transform);
                    totalKeysModified += RequireSuccess(AnimationAuthoringService.SetPreparedKeyframeHold(
                        request.characterClipPath, rootRel, "Transform", "m_LocalRotation",
                        request.impactTime, request.impactTime + request.hitStopDuration, null), "character root hit-stop");
                    totalKeysModified += RequireSuccess(AnimationAuthoringService.SetPreparedKeyframeHold(
                        request.characterClipPath, midRel, "Transform", "m_LocalRotation",
                        request.impactTime, request.impactTime + request.hitStopDuration, null), "character mid hit-stop");
                }

                Vector3 actualEffector = endBone.position;
                Vector3 targetWorld = camera.ViewportToWorldPoint(new Vector3(u, v, depth));
                float reachRatio = 0f;
                Vector3 actualViewport = Vector3.zero;
                AnimationSampling.SampleClip(characterGo, charClip, new[] { request.impactTime }, _ =>
                {
                    if (camClip != null)
                    {
                        AnimationMode.SampleAnimationClip(camera.gameObject, camClip, request.impactTime);
                    }
                    actualEffector = endBone.position;
                    targetWorld = camera.ViewportToWorldPoint(new Vector3(u, v, depth));
                    actualViewport = camera.WorldToViewportPoint(actualEffector);
                    float maxLength = Vector3.Distance(rootBone.position, midBone.position)
                        + Vector3.Distance(midBone.position, endBone.position);
                    reachRatio = maxLength > 0.0001f
                        ? Vector3.Distance(rootBone.position, targetWorld) / maxLength
                        : 1f;
                });

                float pixelWidth = camera.pixelWidth > 0 ? camera.pixelWidth : 1920f;
                float pixelHeight = camera.pixelHeight > 0 ? camera.pixelHeight : 1080f;
                result.impactWorldPosition = new[] { actualEffector.x, actualEffector.y, actualEffector.z };
                result.impactScreenResidualPixels = new[]
                {
                    Mathf.Abs(actualViewport.x - u) * pixelWidth,
                    Mathf.Abs(actualViewport.y - v) * pixelHeight,
                };
                result.maxLimbReachRatio = reachRatio;
                if (reachRatio > 0.98f)
                {
                    result.warnings.Add($"Limb reach ratio is high ({reachRatio * 100f:F1}%). Limb will be near full extension.");
                }

                charClip.EnsureQuaternionContinuity();
                if (camClip != null) camClip.EnsureQuaternionContinuity();
                EditorUtility.SetDirty(charClip);
                if (camClip != null) EditorUtility.SetDirty(camClip);
                Undo.CollapseUndoOperations(undoGroup);
                AssetDatabase.SaveAssets();

                result.success = true;
                result.keyframesModifiedCount = totalKeysModified;
                return result;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                var rollbackEntries = new List<AnimationRollbackEntry>
                {
                    new AnimationRollbackEntry
                    {
                        clipPath = request.characterClipPath,
                        clip = charClip,
                        backupId = result.characterBackupId,
                        label = "Character clip",
                    },
                };
                if (camClip != null)
                {
                    rollbackEntries.Add(new AnimationRollbackEntry
                    {
                        clipPath = request.cameraClipPath,
                        clip = camClip,
                        backupId = result.cameraBackupId,
                        label = "Camera clip",
                    });
                }
                AnimationRollbackService.RevertUndoThenRestore(undoGroup, rollbackEntries, result.warnings);
                return result;
            }
        }

        private static int RequireSuccess(AnimationClipEditResult edit, string label)
        {
            if (edit == null || !edit.success)
            {
                throw new InvalidOperationException($"{label} failed: {edit?.error ?? "no result"}");
            }
            return edit.channelsAffected?.Count ?? 0;
        }
    }
}
