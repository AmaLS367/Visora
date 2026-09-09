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

        private const float IkEpsilon = 1e-5f;

        /// <summary>Angle (radians) opposite side <paramref name="opposite"/> in a triangle with the other two sides.</summary>
        private static float TriangleAngle(float opposite, float adjacent1, float adjacent2)
        {
            float denom = 2f * adjacent1 * adjacent2;
            if (denom < IkEpsilon) return 0f;
            float cos = ((adjacent1 * adjacent1) + (adjacent2 * adjacent2) - (opposite * opposite)) / denom;
            return Mathf.Acos(Mathf.Clamp(cos, -1f, 1f));
        }

        /// <summary>
        /// Analytic two-bone IK. Rotates the mid joint to the law-of-cosines interior angle, aims
        /// the chain at the target, then rolls the chain around the root-&gt;target axis so the mid
        /// joint sits in the plane defined by the pole vector. Degenerate rigs (zero-length bone
        /// or target coincident with the root) are left untouched and reported via
        /// <paramref name="clamped"/> + a NaN-free zero residual is avoided by returning early.
        /// </summary>
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
            clamped = false;
            rotResidualDeg = 0f;

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

            // Degenerate: a collapsed rig (l1 or l2 == 0) or a target on top of the root joint
            // would divide by zero in the law of cosines and write NaN quaternions to the skeleton.
            if (l1 < IkEpsilon || l2 < IkEpsilon || actualDistance < IkEpsilon)
            {
                clamped = true;
                posResidual = actualDistance;
                return;
            }

            // Clamp reach: keep strictly inside [|l1-l2|, l1+l2] with soft damping near extension.
            float softThreshold = maxLen * 0.96f;
            float targetDist = actualDistance;
            if (targetDist > softThreshold)
            {
                float da = maxLen - softThreshold;
                targetDist = softThreshold + (da * (1f - Mathf.Exp(-(actualDistance - softThreshold) / Mathf.Max(da, IkEpsilon))));
                clamped = true;
            }
            float lo = minLen + 0.002f;
            float hi = maxLen * 0.999f;
            if (targetDist < lo) { targetDist = lo; clamped = true; }
            else if (targetDist > hi) { targetDist = hi; clamped = true; }

            // Bend axis: prefer the pole-defined plane, fall back to the current chain plane, then root.right.
            Vector3 axisDir = targetDir / actualDistance;
            Vector3 currentBend = Vector3.Cross(c - a, b - a);
            Vector3 bendNormal;
            if (poleVector.HasValue)
            {
                Vector3 poleDir = poleVector.Value - a;
                Vector3 poleProj = poleDir - (Vector3.Dot(poleDir, axisDir) * axisDir);
                bendNormal = poleProj.sqrMagnitude > IkEpsilon
                    ? Vector3.Cross(axisDir, poleProj)
                    : currentBend;
            }
            else
            {
                bendNormal = currentBend;
            }
            if (bendNormal.sqrMagnitude < IkEpsilon) bendNormal = Vector3.Cross(axisDir, root.right);
            if (bendNormal.sqrMagnitude < IkEpsilon) bendNormal = Vector3.Cross(axisDir, root.up);
            bendNormal.Normalize();

            // 1. Set the interior mid-joint angle via law of cosines.
            float midAngle0 = TriangleAngle((c - a).magnitude, l1, l2);
            float midAngle1 = TriangleAngle(targetDist, l1, l2);
            Vector3 curMidAxis = Vector3.Cross(a - b, c - b);
            if (curMidAxis.sqrMagnitude < IkEpsilon) curMidAxis = bendNormal;
            Quaternion midDelta = Quaternion.AngleAxis((midAngle1 - midAngle0) * Mathf.Rad2Deg, curMidAxis.normalized);
            ApplyWorldRotation(mid, midDelta, weight);

            // 2. Aim the chain so the end lands on the (clamped) target direction.
            c = end.position;
            Vector3 acDir = (c - a).normalized;
            if (acDir.sqrMagnitude > IkEpsilon)
            {
                float aimAngle = Vector3.Angle(acDir, axisDir);
                Vector3 aimAxis = Vector3.Cross(acDir, axisDir);
                if (aimAxis.sqrMagnitude < IkEpsilon) aimAxis = bendNormal;
                Quaternion rootAim = Quaternion.AngleAxis(aimAngle, aimAxis.normalized);
                ApplyWorldRotation(root, rootAim, weight);
            }

            // 3. Roll the chain around the root->target axis so the mid joint sits in the pole plane.
            b = mid.position;
            Vector3 abProj = (b - a) - (Vector3.Dot(b - a, axisDir) * axisDir);
            Vector3 poleTarget = Vector3.Cross(bendNormal, axisDir); // in-plane direction the elbow should point
            if (abProj.sqrMagnitude > IkEpsilon && poleTarget.sqrMagnitude > IkEpsilon)
            {
                float rollAngle = Vector3.SignedAngle(abProj, poleTarget, axisDir);
                Quaternion rollRot = Quaternion.AngleAxis(rollAngle, axisDir);
                ApplyWorldRotation(root, rollRot, weight);
            }

            // 4. Optional effector orientation matching.
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

        /// <summary>Applies a world-space delta rotation to <paramref name="t"/>, blended by <paramref name="weight"/>.</summary>
        private static void ApplyWorldRotation(Transform t, Quaternion worldDelta, float weight)
        {
            Quaternion target = worldDelta * t.rotation;
            t.rotation = weight >= 0.999f ? target : Quaternion.Slerp(t.rotation, target, weight);
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
            float? sampleTime,
            bool deferRestore = false)
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

            // A bake target with no sample time silently no-ops without this guard.
            if (!string.IsNullOrEmpty(bakeToClip) && !sampleTime.HasValue)
            {
                result.success = false;
                result.error = "sample_time is required when bake_to_clip is set.";
                return result;
            }

            // Save initial pose so a query-mode solve can be reverted after measurement.
            Quaternion initRoot = root.localRotation;
            Quaternion initMid = mid.localRotation;
            Quaternion initEnd = end.localRotation;

            // Undo must snapshot the pre-solve pose; recording it after mutation makes undo a no-op.
            if (applyToScene)
            {
                Undo.RecordObjects(new UnityEngine.Object[] { root, mid, end }, "Visora: Solve Two-Bone IK");
            }

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

            if (applyToScene)
            {
                EditorUtility.SetDirty(root);
                EditorUtility.SetDirty(mid);
                EditorUtility.SetDirty(end);
            }
            else if (!deferRestore)
            {
                // Restore initial pose if scene mutation was not requested.
                root.localRotation = initRoot;
                mid.localRotation = initMid;
                end.localRotation = initEnd;
            }

            result.success = true;
            return result;
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

            string backupId = null;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "two_bone_ik");
                result.backupId = backupId;

                int undoGroup = Undo.GetCurrentGroup();
                Undo.IncrementCurrentGroup();
                Undo.SetCurrentGroupName("Visora: Bake Two-Bone IK");
                Undo.RecordObject(clip, "Visora: Bake Two-Bone IK");

                AnimationCurveWriter.WriteQuaternionKey(clip, targetGo.transform, root, time, rootRot);
                AnimationCurveWriter.WriteQuaternionKey(clip, targetGo.transform, mid, time, midRot);
                AnimationCurveWriter.WriteQuaternionKey(clip, targetGo.transform, end, time, endRot);

                clip.EnsureQuaternionContinuity();
                EditorUtility.SetDirty(clip);
                AssetDatabase.SaveAssets();
                Undo.CollapseUndoOperations(undoGroup);
            }
            catch (Exception ex)
            {
                result.warnings.Add($"Error baking to clip: {ex.Message}");
                if (!string.IsNullOrEmpty(backupId))
                {
                    try
                    {
                        AnimationBackupService.RestoreBackup(clip, clipPath, backupId, null);
                        AssetDatabase.SaveAssets();
                        result.warnings.Add("Clip restored from pre-bake backup after the failure.");
                    }
                    catch (Exception restoreEx)
                    {
                        result.warnings.Add($"Rollback also failed: {restoreEx.Message}");
                    }
                }
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

            // Snapshot the limb so query-mode metrics can be read from the SOLVED pose before revert.
            var targetGo = GameObject.Find(targetObjectPath);
            ResolveLimbTransforms(targetGo, effector, rootBone, midBone, endBone,
                out var snapRoot, out var snapMid, out var endTransform, out _);
            Quaternion snapRootRot = snapRoot != null ? snapRoot.localRotation : Quaternion.identity;
            Quaternion snapMidRot = snapMid != null ? snapMid.localRotation : Quaternion.identity;
            Quaternion snapEndRot = endTransform != null ? endTransform.localRotation : Quaternion.identity;

            bool restoreQueryPose = !applyToScene && snapRoot != null && snapMid != null && endTransform != null;
            try
            {
                // Keep the solved pose in place (deferRestore) until every viewport metric is captured.
                var ikResult = SolveTwoBoneIK(
                    targetObjectPath, effector, rootBone, midBone, endBone,
                    new[] { worldTarget.x, worldTarget.y, worldTarget.z },
                    targetRotArr, poleVectorArray, "world", cameraName, weight, applyToScene, bakeToClip, sampleTime,
                    deferRestore: true);

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

                Vector3 solvedWorld = endTransform.position;
                res.solvedWorldPosition = new[] { solvedWorld.x, solvedWorld.y, solvedWorld.z };
                Vector3 actualVp = cam.WorldToViewportPoint(solvedWorld);
                res.actualViewport = new[] { actualVp.x, actualVp.y, actualVp.z };

                float pixelWidth = cam.pixelWidth > 0 ? cam.pixelWidth : 1920f;
                float pixelHeight = cam.pixelHeight > 0 ? cam.pixelHeight : 1080f;
                res.screenResidualPixels = new[]
                {
                    (actualVp.x - viewportX) * pixelWidth,
                    (actualVp.y - viewportY) * pixelHeight,
                };
                res.depthResidualMeters = Mathf.Abs(actualVp.z - cameraDepth);
                res.isInFrustum = actualVp.z > 0f && actualVp.x >= 0f && actualVp.x <= 1f
                    && actualVp.y >= 0f && actualVp.y <= 1f;
                res.isClippedByNearPlane = actualVp.z <= cam.nearClipPlane;
                res.success = true;
                return res;
            }
            finally
            {
                if (restoreQueryPose)
                {
                    snapRoot.localRotation = snapRootRot;
                    snapMid.localRotation = snapMidRot;
                    endTransform.localRotation = snapEndRot;
                }
            }
        }
    }
}
