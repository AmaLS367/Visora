using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class NativeTwoBoneIKResult
    {
        public bool success = true;
        public string error;
        public string targetObjectPath;
        public string effector;
        public string rootBone;
        public string midBone;
        public string endBone;
        public float[] rootRotationEuler;
        public float[] rootRotationQuaternion;
        public float[] midRotationEuler;
        public float[] midRotationQuaternion;
        public float[] endRotationEuler;
        public float[] endRotationQuaternion;
        public bool targetClamped;
        public float reachDistance;
        public float actualDistance;
        public float positionResidual;
        public float rotationResidualDeg;
        public string backupId;
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class NativeViewportPlacementResult
    {
        public bool success = true;
        public string error;
        public string cameraName;
        public string targetObjectPath;
        public string effector;
        public float[] targetWorldPosition;
        public float[] solvedWorldPosition;
        public float[] actualViewport;
        public float[] screenResidualPixels;
        public float depthResidualMeters;
        public bool isInFrustum;
        public bool isClippedByNearPlane;
        public float reachDistance;
        public float actualDistance;
        public bool targetClamped;
        public NativeTwoBoneIKResult ikResult;
        public List<string> warnings = new List<string>();
    }

    public static class InverseKinematicsService
    {
        public static Transform FindTransformFuzzy(Transform[] transforms, params string[] patterns)
        {
            if (transforms == null) return null;
            for (int p = 0; p < patterns.Length; p++)
            {
                string pat = patterns[p];
                for (int i = 0; i < transforms.Length; i++)
                {
                    var t = transforms[i];
                    if (t != null && t.name.Contains(pat, StringComparison.OrdinalIgnoreCase))
                        return t;
                }
            }
            return null;
        }

        public static bool ResolveLimbTransforms(
            GameObject rootGo,
            string effector,
            string rootBone,
            string midBone,
            string endBone,
            out Transform root,
            out Transform mid,
            out Transform end,
            out string blocker)
        {
            root = null;
            mid = null;
            end = null;
            blocker = null;

            if (rootGo == null)
            {
                blocker = "Target GameObject not found in scene.";
                return false;
            }

            var animator = rootGo.GetComponentInChildren<Animator>();
            bool isHuman = animator != null && animator.avatar != null && animator.avatar.isValid && animator.avatar.isHuman;
            Transform[] cached = rootGo.GetComponentsInChildren<Transform>(true);

            if (!string.IsNullOrEmpty(effector))
            {
                string eff = effector.ToLowerInvariant();
                if (eff == "left_foot")
                {
                    if (isHuman)
                    {
                        root = animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg);
                        mid = animator.GetBoneTransform(HumanBodyBones.LeftLowerLeg);
                        end = animator.GetBoneTransform(HumanBodyBones.LeftFoot);
                    }
                    if (root == null) root = FindTransformFuzzy(cached, "LeftUpperLeg", "thigh_l", "upperleg_l", "leftupleg");
                    if (mid == null) mid = FindTransformFuzzy(cached, "LeftLowerLeg", "calf_l", "lowerleg_l", "knee_l", "leftleg");
                    if (end == null) end = FindTransformFuzzy(cached, "LeftFoot", "foot_l", "ankle_l", "leftfoot");
                }
                else if (eff == "right_foot")
                {
                    if (isHuman)
                    {
                        root = animator.GetBoneTransform(HumanBodyBones.RightUpperLeg);
                        mid = animator.GetBoneTransform(HumanBodyBones.RightLowerLeg);
                        end = animator.GetBoneTransform(HumanBodyBones.RightFoot);
                    }
                    if (root == null) root = FindTransformFuzzy(cached, "RightUpperLeg", "thigh_r", "upperleg_r", "rightupleg");
                    if (mid == null) mid = FindTransformFuzzy(cached, "RightLowerLeg", "calf_r", "lowerleg_r", "knee_r", "rightleg");
                    if (end == null) end = FindTransformFuzzy(cached, "RightFoot", "foot_r", "ankle_r", "rightfoot");
                }
                else if (eff == "left_hand")
                {
                    if (isHuman)
                    {
                        root = animator.GetBoneTransform(HumanBodyBones.LeftUpperArm);
                        mid = animator.GetBoneTransform(HumanBodyBones.LeftLowerArm);
                        end = animator.GetBoneTransform(HumanBodyBones.LeftHand);
                    }
                    if (root == null) root = FindTransformFuzzy(cached, "LeftUpperArm", "upperarm_l", "arm_l", "leftarm");
                    if (mid == null) mid = FindTransformFuzzy(cached, "LeftLowerArm", "forearm_l", "lowerarm_l", "elbow_l");
                    if (end == null) end = FindTransformFuzzy(cached, "LeftHand", "hand_l", "wrist_l", "lefthand");
                }
                else if (eff == "right_hand")
                {
                    if (isHuman)
                    {
                        root = animator.GetBoneTransform(HumanBodyBones.RightUpperArm);
                        mid = animator.GetBoneTransform(HumanBodyBones.RightLowerArm);
                        end = animator.GetBoneTransform(HumanBodyBones.RightHand);
                    }
                    if (root == null) root = FindTransformFuzzy(cached, "RightUpperArm", "upperarm_r", "arm_r", "rightarm");
                    if (mid == null) mid = FindTransformFuzzy(cached, "RightLowerArm", "forearm_r", "lowerarm_r", "elbow_r");
                    if (end == null) end = FindTransformFuzzy(cached, "RightHand", "hand_r", "wrist_r", "righthand");
                }
                else
                {
                    blocker = $"Unsupported effector name '{effector}'. Use 'left_foot', 'right_foot', 'left_hand', 'right_hand', or provide explicit bone paths.";
                    return false;
                }
            }
            else
            {
                if (!string.IsNullOrEmpty(rootBone)) root = FindTransformFuzzy(cached, rootBone);
                if (!string.IsNullOrEmpty(midBone)) mid = FindTransformFuzzy(cached, midBone);
                if (!string.IsNullOrEmpty(endBone)) end = FindTransformFuzzy(cached, endBone);
            }

            if (root == null || mid == null || end == null)
            {
                blocker = $"Incomplete 3-bone chain (Root: {root?.name ?? "null"}, Mid: {mid?.name ?? "null"}, End: {end?.name ?? "null"}).";
                return false;
            }

            return true;
        }

        public static void SolveTwoBoneIKInternal(
            Transform root,
            Transform mid,
            Transform end,
            Vector3 targetPos,
            Quaternion? targetRot,
            Vector3? poleVector,
            float weight,
            out bool clamped,
            out float reachDistance,
            out float actualDistance,
            out float posResidual,
            out float rotResidualDeg)
        {
            Vector3 a = root.position;
            Vector3 b = mid.position;
            Vector3 c = end.position;

            float l1 = Vector3.Distance(a, b);
            float l2 = Vector3.Distance(b, c);
            float maxLen = l1 + l2;
            float minLen = Mathf.Abs(l1 - l2);
            reachDistance = maxLen;

            Vector3 targetDir = targetPos - a;
            actualDistance = targetDir.magnitude;
            clamped = false;

            // Soft damping near full extension to prevent violent snaps
            float softThreshold = maxLen * 0.96f;
            float targetDist = actualDistance;
            if (targetDist > softThreshold)
            {
                float da = maxLen - softThreshold;
                targetDist = softThreshold + da * (1f - Mathf.Exp(-(actualDistance - softThreshold) / Mathf.Max(da, 0.0001f)));
                clamped = true;
            }

            if (targetDist < minLen + 0.002f)
            {
                targetDist = minLen + 0.002f;
                clamped = true;
            }
            else if (targetDist > maxLen * 0.999f)
            {
                targetDist = maxLen * 0.999f;
                clamped = true;
            }

            // Determine bend plane
            Vector3 bendNormal;
            if (poleVector.HasValue)
            {
                Vector3 poleDir = poleVector.Value - a;
                bendNormal = Vector3.Cross(targetDir, poleDir);
                if (bendNormal.sqrMagnitude < 0.0001f)
                {
                    bendNormal = Vector3.Cross(b - a, c - a);
                }
            }
            else
            {
                bendNormal = Vector3.Cross(b - a, c - a);
            }

            if (bendNormal.sqrMagnitude < 0.0001f)
            {
                bendNormal = root.right;
            }
            bendNormal.Normalize();

            // Law of Cosines
            float cosAlpha = ((l1 * l1) + (targetDist * targetDist) - (l2 * l2)) / (2f * l1 * targetDist);
            float alpha = Mathf.Acos(Mathf.Clamp(cosAlpha, -1f, 1f)) * Mathf.Rad2Deg;

            float cosBeta = ((l1 * l1) + (l2 * l2) - (targetDist * targetDist)) / (2f * l1 * l2);
            float beta = Mathf.Acos(Mathf.Clamp(cosBeta, -1f, 1f)) * Mathf.Rad2Deg;

            // Root rotation
            Vector3 targetDirNorm = targetDir.normalized;
            Quaternion targetRotRoot = Quaternion.AngleAxis(-alpha, bendNormal) * Quaternion.LookRotation(targetDirNorm, bendNormal);
            Quaternion rootDelta = targetRotRoot * Quaternion.Inverse(root.rotation);
            Quaternion solvedRootRot = Quaternion.Slerp(root.rotation, rootDelta * root.rotation, weight);
            root.rotation = solvedRootRot;

            // Mid rotation (bend)
            Vector3 desiredEndDir = (targetPos - mid.position).normalized;
            Quaternion midDelta = Quaternion.FromToRotation((end.position - mid.position).normalized, desiredEndDir);
            Quaternion solvedMidRot = Quaternion.Slerp(mid.rotation, midDelta * mid.rotation, weight);
            mid.rotation = solvedMidRot;

            // End rotation (optional effector orientation matching)
            rotResidualDeg = 0f;
            if (targetRot.HasValue)
            {
                Quaternion targetEndRot = targetRot.Value;
                Quaternion endDelta = targetEndRot * Quaternion.Inverse(end.rotation);
                Quaternion solvedEndRot = Quaternion.Slerp(end.rotation, endDelta * end.rotation, weight);
                end.rotation = solvedEndRot;
                rotResidualDeg = Quaternion.Angle(end.rotation, targetEndRot);
            }

            posResidual = Vector3.Distance(end.position, targetPos);
        }

        public static NativeTwoBoneIKResult SolveTwoBoneIK(
            string targetObjectPath,
            string effector,
            string rootBone,
            string midBone,
            string endBone,
            float[] targetPosArray,
            float[] targetRotArray,
            float[] poleVectorArray,
            string space,
            string cameraName,
            float weight,
            bool applyToScene,
            string bakeToClip,
            float? sampleTime)
        {
            var result = new NativeTwoBoneIKResult
            {
                targetObjectPath = targetObjectPath,
                effector = effector,
                rootBone = rootBone,
                midBone = midBone,
                endBone = endBone,
            };

            var targetGo = GameObject.Find(targetObjectPath);
            if (targetGo == null)
            {
                result.success = false;
                result.error = $"GameObject at '{targetObjectPath}' was not found in active scene.";
                return result;
            }

            if (!ResolveLimbTransforms(targetGo, effector, rootBone, midBone, endBone, out var root, out var mid, out var end, out var blocker))
            {
                result.success = false;
                result.error = blocker;
                return result;
            }

            result.rootBone = root.name;
            result.midBone = mid.name;
            result.endBone = end.name;

            if (targetPosArray == null || targetPosArray.Length < 3)
            {
                result.success = false;
                result.error = "targetPosition must contain at least 3 coordinates [x, y, z].";
                return result;
            }

            Vector3 targetPos = new Vector3(targetPosArray[0], targetPosArray[1], targetPosArray[2]);
            string sp = (space ?? "world").ToLowerInvariant();
            if (sp == "local" && root.parent != null)
            {
                targetPos = root.parent.TransformPoint(targetPos);
            }
            else if (sp == "camera")
            {
                var cam = CameraRenderingService.FindCamera(cameraName);
                if (cam != null)
                {
                    targetPos = cam.transform.TransformPoint(targetPos);
                }
                else
                {
                    result.warnings.Add($"Camera '{cameraName}' not found; assuming world space target position.");
                }
            }

            Quaternion? targetRot = null;
            if (targetRotArray != null)
            {
                if (targetRotArray.Length == 4)
                {
                    targetRot = new Quaternion(targetRotArray[0], targetRotArray[1], targetRotArray[2], targetRotArray[3]);
                }
                else if (targetRotArray.Length == 3)
                {
                    targetRot = Quaternion.Euler(targetRotArray[0], targetRotArray[1], targetRotArray[2]);
                }
            }

            Vector3? poleVector = null;
            if (poleVectorArray != null && poleVectorArray.Length >= 3)
            {
                poleVector = new Vector3(poleVectorArray[0], poleVectorArray[1], poleVectorArray[2]);
            }

            // Save initial pose if not applying to scene permanently
            Quaternion initRoot = root.localRotation;
            Quaternion initMid = mid.localRotation;
            Quaternion initEnd = end.localRotation;

            SolveTwoBoneIKInternal(
                root, mid, end, targetPos, targetRot, poleVector, Mathf.Clamp01(weight),
                out bool clamped, out float reachDist, out float actualDist, out float posResidual, out float rotResidualDeg);

            result.targetClamped = clamped;
            result.reachDistance = reachDist;
            result.actualDistance = actualDist;
            result.positionResidual = posResidual;
            result.rotationResidualDeg = rotResidualDeg;

            // Output solved local rotations
            Vector3 rootEuler = root.localEulerAngles;
            Quaternion rootQuat = root.localRotation;
            Vector3 midEuler = mid.localEulerAngles;
            Quaternion midQuat = mid.localRotation;
            Vector3 endEuler = end.localEulerAngles;
            Quaternion endQuat = end.localRotation;

            result.rootRotationEuler = new[] { rootEuler.x, rootEuler.y, rootEuler.z };
            result.rootRotationQuaternion = new[] { rootQuat.x, rootQuat.y, rootQuat.z, rootQuat.w };
            result.midRotationEuler = new[] { midEuler.x, midEuler.y, midEuler.z };
            result.midRotationQuaternion = new[] { midQuat.x, midQuat.y, midQuat.z, midQuat.w };
            result.endRotationEuler = new[] { endEuler.x, endEuler.y, endEuler.z };
            result.endRotationQuaternion = new[] { endQuat.x, endQuat.y, endQuat.z, endQuat.w };

            // Optional baking to AnimationClip
            if (!string.IsNullOrEmpty(bakeToClip) && sampleTime.HasValue)
            {
                string editModeErr = AnimationBackupService.CheckEditMode();
                if (editModeErr != null)
                {
                    result.warnings.Add($"Baking skipped: {editModeErr}");
                }
                else
                {
                    BakeIKToClip(bakeToClip, targetGo, root, mid, end, sampleTime.Value, rootQuat, midQuat, endQuat, result);
                }
            }

            if (!applyToScene)
            {
                // Restore initial pose if scene mutation was not requested
                root.localRotation = initRoot;
                mid.localRotation = initMid;
                end.localRotation = initEnd;
            }
            else
            {
                Undo.RecordObjects(new UnityEngine.Object[] { root, mid, end }, "Visora: Solve Two-Bone IK");
            }

            result.success = true;
            return result;
        }

        private static string GetRelativeHierarchyPath(Transform root, Transform target)
        {
            if (root == target) return "";
            var path = new List<string>();
            var current = target;
            while (current != null && current != root)
            {
                path.Add(current.name);
                current = current.parent;
            }
            path.Reverse();
            return string.Join("/", path);
        }

        private static void BakeIKToClip(
            string clipPath,
            GameObject targetGo,
            Transform root,
            Transform mid,
            Transform end,
            float time,
            Quaternion rootRot,
            Quaternion midRot,
            Quaternion endRot,
            NativeTwoBoneIKResult result)
        {
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            if (clip == null)
            {
                result.warnings.Add($"Failed to bake: AnimationClip not found at '{clipPath}'.");
                return;
            }

            try
            {
                string backupId = AnimationBackupService.WriteBackup(clip, clipPath, "two_bone_ik");
                result.backupId = backupId;

                int undoGroup = Undo.GetCurrentGroup();
                Undo.IncrementCurrentGroup();
                Undo.SetCurrentGroupName("Visora: Bake Two-Bone IK");
                Undo.RecordObject(clip, "Visora: Bake Two-Bone IK");

                // Write quaternion curves for root, mid, end
                WriteBoneQuaternionCurves(clip, targetGo.transform, root, time, rootRot);
                WriteBoneQuaternionCurves(clip, targetGo.transform, mid, time, midRot);
                WriteBoneQuaternionCurves(clip, targetGo.transform, end, time, endRot);

                clip.EnsureQuaternionContinuity();
                EditorUtility.SetDirty(clip);
                AssetDatabase.SaveAssets();
                Undo.CollapseUndoOperations(undoGroup);
            }
            catch (Exception ex)
            {
                result.warnings.Add($"Error baking to clip: {ex.Message}");
            }
        }

        private static void WriteBoneQuaternionCurves(
            AnimationClip clip,
            Transform rootTransform,
            Transform bone,
            float time,
            Quaternion localRot)
        {
            string bonePath = GetRelativeHierarchyPath(rootTransform, bone);
            string[] props = { "m_LocalRotation.x", "m_LocalRotation.y", "m_LocalRotation.z", "m_LocalRotation.w" };
            float[] vals = { localRot.x, localRot.y, localRot.z, localRot.w };

            for (int i = 0; i < 4; i++)
            {
                var binding = EditorCurveBinding.FloatCurve(bonePath, typeof(Transform), props[i]);
                var curve = AnimationUtility.GetEditorCurve(clip, binding) ?? new AnimationCurve();
                bool replaced = false;
                for (int k = 0; k < curve.length; k++)
                {
                    if (Mathf.Abs(curve[k].time - time) < 0.0001f)
                    {
                        curve.MoveKey(k, new Keyframe(time, vals[i]));
                        replaced = true;
                        break;
                    }
                }
                if (!replaced)
                {
                    curve.AddKey(time, vals[i]);
                }
                AnimationUtility.SetEditorCurve(clip, binding, curve);
            }
        }

        public static NativeViewportPlacementResult PlaceEffectorInViewport(
            string cameraName,
            string targetObjectPath,
            string effector,
            string rootBone,
            string midBone,
            string endBone,
            float viewportX,
            float viewportY,
            float cameraDepth,
            string alignMode,
            float[] customRotationArray,
            float[] poleVectorArray,
            float weight,
            bool applyToScene,
            string bakeToClip,
            float? sampleTime)
        {
            var res = new NativeViewportPlacementResult
            {
                cameraName = cameraName,
                targetObjectPath = targetObjectPath,
                effector = effector,
            };

            var cam = CameraRenderingService.FindCamera(cameraName);
            if (cam == null)
            {
                res.success = false;
                res.error = $"Camera '{cameraName}' was not found in the active scene.";
                return res;
            }

            if (cameraDepth <= 0.001f)
            {
                res.success = false;
                res.error = "cameraDepth must be greater than 0.001 meters.";
                return res;
            }

            // Viewport to World conversion
            Vector3 viewportTarget = new Vector3(viewportX, viewportY, cameraDepth);
            Vector3 worldTarget = cam.ViewportToWorldPoint(viewportTarget);
            res.targetWorldPosition = new[] { worldTarget.x, worldTarget.y, worldTarget.z };

            // Determine target rotation
            Quaternion? targetRot = null;
            string mode = (alignMode ?? "face_camera").ToLowerInvariant();
            if (mode == "face_camera")
            {
                // Align sole/palm facing camera lens
                Vector3 toCam = (cam.transform.position - worldTarget).normalized;
                targetRot = Quaternion.LookRotation(toCam, cam.transform.up);
            }
            else if (mode == "match_camera_rotation")
            {
                targetRot = cam.transform.rotation;
            }
            else if (mode == "custom" && customRotationArray != null)
            {
                if (customRotationArray.Length == 4)
                    targetRot = new Quaternion(customRotationArray[0], customRotationArray[1], customRotationArray[2], customRotationArray[3]);
                else if (customRotationArray.Length == 3)
                    targetRot = Quaternion.Euler(customRotationArray[0], customRotationArray[1], customRotationArray[2]);
            }

            float[] targetRotArr = null;
            if (targetRot.HasValue)
            {
                targetRotArr = new[] { targetRot.Value.x, targetRot.Value.y, targetRot.Value.z, targetRot.Value.w };
            }

            // Solve Two-Bone IK
            var ikResult = SolveTwoBoneIK(
                targetObjectPath, effector, rootBone, midBone, endBone,
                new[] { worldTarget.x, worldTarget.y, worldTarget.z },
                targetRotArr, poleVectorArray, "world", cameraName, weight, applyToScene, bakeToClip, sampleTime);

            res.ikResult = ikResult;
            if (!ikResult.success)
            {
                res.success = false;
                res.error = ikResult.error;
                return res;
            }

            res.reachDistance = ikResult.reachDistance;
            res.actualDistance = ikResult.actualDistance;
            res.targetClamped = ikResult.targetClamped;

            // Find end transform to measure actual solved position
            var targetGo = GameObject.Find(targetObjectPath);
            ResolveLimbTransforms(targetGo, effector, rootBone, midBone, endBone, out _, out _, out var endTransform, out _);
            if (endTransform != null)
            {
                Vector3 solvedWorld = endTransform.position;
                res.solvedWorldPosition = new[] { solvedWorld.x, solvedWorld.y, solvedWorld.z };

                // Reproject through camera
                Vector3 actualVp = cam.WorldToViewportPoint(solvedWorld);
                res.actualViewport = new[] { actualVp.x, actualVp.y, actualVp.z };

                float pixelWidth = cam.pixelWidth > 0 ? cam.pixelWidth : 1920f;
                float pixelHeight = cam.pixelHeight > 0 ? cam.pixelHeight : 1080f;
                float residualPixelX = (actualVp.x - viewportX) * pixelWidth;
                float residualPixelY = (actualVp.y - viewportY) * pixelHeight;
                res.screenResidualPixels = new[] { residualPixelX, residualPixelY };
                res.depthResidualMeters = Mathf.Abs(actualVp.z - cameraDepth);

                res.isInFrustum = actualVp.z > 0f && actualVp.x >= 0f && actualVp.x <= 1f && actualVp.y >= 0f && actualVp.y <= 1f;
                res.isClippedByNearPlane = actualVp.z <= cam.nearClipPlane;
            }

            res.success = true;
            return res;
        }
    }
}
