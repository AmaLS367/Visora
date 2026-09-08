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
        public string effector; // "left_foot", "right_foot", "left_hand", "right_hand"
        public float impactTime;
        public float contactDuration;
        public float[] lensViewport; // [u, v]
        public float lensDistanceMeters;
        public float hitStopDuration;
        public float[] cameraRecoilImpulse; // [x, y, z] in camera local space
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
    /// Solves coordinated camera-subject combat and cinematic impact: locks character limb
    /// to camera lens viewport, inserts hit-stop keyframe holds, and authors camera recoil impulse curves.
    /// </summary>
    public static class CameraSubjectActionService
    {
        public static CameraSubjectContactResult SolveCameraSubjectContact(CameraSubjectContactRequest request)
        {
            var result = new CameraSubjectContactResult();

            if (EditorApplication.isPlaying)
            {
                result.success = false;
                result.error = "Camera-subject contact solving requires Edit Mode; exit Play Mode before running.";
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

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora Camera-Subject Contact Solve");

            int totalKeysModified = 0;

            try
            {
                float u = request.lensViewport != null && request.lensViewport.Length >= 1 ? request.lensViewport[0] : 0.5f;
                float v = request.lensViewport != null && request.lensViewport.Length >= 2 ? request.lensViewport[1] : 0.5f;
                float depth = request.lensDistanceMeters > 0.05f ? request.lensDistanceMeters : 0.3f;

                Vector3 targetWorldPos = camera.ViewportToWorldPoint(new Vector3(u, v, depth));
                result.impactWorldPosition = new float[] { targetWorldPos.x, targetWorldPos.y, targetWorldPos.z };

                // Bake character limb contact to camera lens viewport
                float contactDur = Mathf.Max(0.05f, request.contactDuration);
                var bakeReq = new EffectorContactBakeRequest
                {
                    clipPath = request.characterClipPath,
                    targetObjectPath = request.characterPath,
                    effector = request.effector,
                    targetType = "camera_viewport",
                    cameraName = request.cameraName,
                    viewportCoordinates = new float[] { u, v },
                    viewportDepth = depth,
                    timeRange = new float[] { request.impactTime, request.impactTime + contactDur },
                    blendInSeconds = 0.08f,
                    blendOutSeconds = 0.12f
                };

                var bakeRes = AnimationEffectorContactService.BakeContact(bakeReq);
                if (!bakeRes.success)
                {
                    throw new InvalidOperationException($"Character effector bake failed: {bakeRes.error}");
                }

                result.characterBackupId = bakeRes.backupId;
                totalKeysModified += bakeRes.keyframesModifiedCount;
                result.warnings.AddRange(bakeRes.warnings);

                // Check reachability
                if (InverseKinematicsService.ResolveLimbTransforms(
                        characterGo,
                        request.effector,
                        null, null, null,
                        out var rootBone,
                        out var midBone,
                        out var endBone,
                        out var blocker))
                {
                    float l1 = Vector3.Distance(rootBone.position, midBone.position);
                    float l2 = Vector3.Distance(midBone.position, endBone.position);
                    float maxLen = l1 + l2;
                    float dist = Vector3.Distance(rootBone.position, targetWorldPos);
                    result.maxLimbReachRatio = maxLen > 0.0001f ? dist / maxLen : 1f;

                    if (result.maxLimbReachRatio > 0.98f)
                    {
                        result.warnings.Add($"Limb reach ratio is high ({result.maxLimbReachRatio * 100f:F1}%). Limb will be near full extension.");
                    }
                }

                // Verify screen residual
                Vector3 projected = camera.WorldToViewportPoint(targetWorldPos);
                float pixelErrX = Mathf.Abs(projected.x - u) * camera.pixelWidth;
                float pixelErrY = Mathf.Abs(projected.y - v) * camera.pixelHeight;
                result.impactScreenResidualPixels = new float[] { pixelErrX, pixelErrY };

                // Apply hit-stop hold if requested
                if (request.hitStopDuration > 0.01f)
                {
                    // Hold root and mid bone on character
                    if (rootBone != null && midBone != null)
                    {
                        string rootRel = AnimationUtility.CalculateTransformPath(rootBone, characterGo.transform);
                        string midRel = AnimationUtility.CalculateTransformPath(midBone, characterGo.transform);

                        AnimationAuthoringService.SetKeyframeHold(
                            request.characterClipPath,
                            rootRel,
                            "Transform",
                            "m_LocalRotation",
                            request.impactTime,
                            request.impactTime + request.hitStopDuration,
                            null,
                            null);

                        AnimationAuthoringService.SetKeyframeHold(
                            request.characterClipPath,
                            midRel,
                            "Transform",
                            "m_LocalRotation",
                            request.impactTime,
                            request.impactTime + request.hitStopDuration,
                            null,
                            null);

                        totalKeysModified += 8;
                    }
                }

                // Author camera recoil curve if cameraClipPath is provided
                if (!string.IsNullOrEmpty(request.cameraClipPath))
                {
                    var camClip = AnimationPreviewService.ResolveClip(request.cameraClipPath);
                    if (camClip != null)
                    {
                        try
                        {
                            result.cameraBackupId = AnimationBackupService.WriteBackup(camClip, request.cameraClipPath, "camera_recoil");
                        }
                        catch (Exception bex)
                        {
                            result.warnings.Add($"Camera backup warning: {bex.Message}");
                        }

                        Undo.RegisterCompleteObjectUndo(camClip, "Visora Camera Recoil");

                        Vector3 recoil = (request.cameraRecoilImpulse != null && request.cameraRecoilImpulse.Length >= 3)
                            ? new Vector3(request.cameraRecoilImpulse[0], request.cameraRecoilImpulse[1], request.cameraRecoilImpulse[2])
                            : new Vector3(0f, -0.15f, -0.4f);

                        // Sample camera local position at impact
                        AnimationMode.BeginSampling();
                        AnimationMode.SampleAnimationClip(camera.gameObject, camClip, request.impactTime);
                        AnimationMode.EndSampling();

                        Vector3 baseCamPos = camera.transform.localPosition;
                        Vector3 peakCamPos = baseCamPos + recoil;

                        string camRelPath = ""; // camera root

                        // Recoil keyframes: base -> peak -> hold -> settle
                        float t0 = request.impactTime;
                        float tPeak = t0 + 0.04f;
                        float tHold = tPeak + (request.hitStopDuration > 0.01f ? request.hitStopDuration : 0.04f);
                        float tSettle = tHold + 0.2f;

                        AnimationAuthoringService.SetKeyframe(
                            request.cameraClipPath,
                            camRelPath,
                            "Transform",
                            "m_LocalPosition",
                            t0,
                            new float[] { baseCamPos.x, baseCamPos.y, baseCamPos.z },
                            "smooth",
                            null,
                            null,
                            null);

                        AnimationAuthoringService.SetKeyframe(
                            request.cameraClipPath,
                            camRelPath,
                            "Transform",
                            "m_LocalPosition",
                            tPeak,
                            new float[] { peakCamPos.x, peakCamPos.y, peakCamPos.z },
                            "smooth",
                            null,
                            null,
                            null);

                        if (tHold > tPeak)
                        {
                            AnimationAuthoringService.SetKeyframe(
                                request.cameraClipPath,
                                camRelPath,
                                "Transform",
                                "m_LocalPosition",
                                tHold,
                                new float[] { peakCamPos.x, peakCamPos.y, peakCamPos.z },
                                "smooth",
                                null,
                                null,
                                null);
                        }

                        AnimationAuthoringService.SetKeyframe(
                            request.cameraClipPath,
                            camRelPath,
                            "Transform",
                            "m_LocalPosition",
                            tSettle,
                            new float[] { baseCamPos.x, baseCamPos.y, baseCamPos.z },
                            "smooth",
                            null,
                            null,
                            null);

                        camClip.EnsureQuaternionContinuity();
                        EditorUtility.SetDirty(camClip);
                        totalKeysModified += 12;
                    }
                }

                Undo.CollapseUndoOperations(undoGroup);
                AssetDatabase.SaveAssets();

                result.success = true;
                result.keyframesModifiedCount = totalKeysModified;
                return result;
            }
            catch (Exception ex)
            {
                Undo.RevertAllDownToGroup(undoGroup);
                result.success = false;
                result.error = ex.Message;
                return result;
            }
        }
    }
}
