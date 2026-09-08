using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class NativeGazeJointRotation
    {
        public string boneName;
        public float[] localEuler;
        public float[] localQuaternion;
        public float allocatedYawDeg;
        public float allocatedPitchDeg;
        public bool wasClamped;
    }

    [Serializable]
    public class NativeCharacterGazeResult
    {
        public bool success = true;
        public string error;
        public string targetObjectPath;
        public float[] targetLookAtPosition;
        public float totalTargetAngleDeg;
        public bool isTargetBehindCharacter;
        public bool wasClamped;
        public float residualGazeErrorDeg;
        public List<NativeGazeJointRotation> solvedJoints = new List<NativeGazeJointRotation>();
        public string backupId;
        public List<string> warnings = new List<string>();
    }

    public static class GazeService
    {
        private static Transform FindTransformFuzzy(Transform[] transforms, params string[] patterns)
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

        public static NativeCharacterGazeResult SolveCharacterGaze(
            string targetObjectPath,
            float[] targetLookAtPosArray,
            string targetTransformPath,
            float chestWeight,
            float neckWeight,
            float headWeight,
            float eyesWeight,
            float[] upVectorArray,
            bool applyToScene,
            string bakeToClip,
            float? sampleTime)
        {
            var result = new NativeCharacterGazeResult
            {
                targetObjectPath = targetObjectPath
            };

            var targetGo = GameObject.Find(targetObjectPath);
            if (targetGo == null)
            {
                result.success = false;
                result.error = $"GameObject at '{targetObjectPath}' was not found in the active scene.";
                return result;
            }

            // Resolve target look-at position
            Vector3 targetLookAtPos;
            if (!string.IsNullOrEmpty(targetTransformPath))
            {
                if (targetTransformPath.StartsWith("camera:", StringComparison.OrdinalIgnoreCase))
                {
                    string camName = targetTransformPath.Substring("camera:".Length).Trim();
                    var cam = CameraRenderingService.FindCamera(camName);
                    if (cam == null)
                    {
                        result.success = false;
                        result.error = $"Target camera '{camName}' not found in the scene.";
                        return result;
                    }
                    targetLookAtPos = cam.transform.position;
                }
                else
                {
                    var tGo = GameObject.Find(targetTransformPath);
                    if (tGo == null)
                    {
                        result.success = false;
                        result.error = $"Target transform GameObject '{targetTransformPath}' not found.";
                        return result;
                    }
                    targetLookAtPos = tGo.transform.position;
                }
            }
            else if (targetLookAtPosArray != null && targetLookAtPosArray.Length >= 3)
            {
                targetLookAtPos = new Vector3(targetLookAtPosArray[0], targetLookAtPosArray[1], targetLookAtPosArray[2]);
            }
            else
            {
                result.success = false;
                result.error = "Neither targetLookAtPosArray nor targetTransformPath was specified.";
                return result;
            }

            result.targetLookAtPosition = new[] { targetLookAtPos.x, targetLookAtPos.y, targetLookAtPos.z };

            // Resolve character bones
            var animator = targetGo.GetComponentInChildren<Animator>();
            bool isHuman = animator != null && animator.avatar != null && animator.avatar.isValid && animator.avatar.isHuman;
            Transform[] cached = targetGo.GetComponentsInChildren<Transform>(true);

            Transform chest = isHuman ? animator.GetBoneTransform(HumanBodyBones.Chest) : null;
            if (chest == null && isHuman) chest = animator.GetBoneTransform(HumanBodyBones.Spine);
            if (chest == null) chest = FindTransformFuzzy(cached, "Chest", "spine1", "spine2", "spine");

            Transform neck = isHuman ? animator.GetBoneTransform(HumanBodyBones.Neck) : null;
            if (neck == null) neck = FindTransformFuzzy(cached, "Neck", "neck1");

            Transform head = isHuman ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
            if (head == null) head = FindTransformFuzzy(cached, "Head");

            if (head == null)
            {
                result.success = false;
                result.error = "Head transform could not be resolved on target character.";
                return result;
            }

            Vector3 upVector = Vector3.up;
            if (upVectorArray != null && upVectorArray.Length >= 3)
            {
                upVector = new Vector3(upVectorArray[0], upVectorArray[1], upVectorArray[2]).normalized;
            }

            // Normalise weights
            float totalWeight = Mathf.Max(0.0001f, chestWeight + neckWeight + headWeight + eyesWeight);
            float wChest = chestWeight / totalWeight;
            float wNeck = neckWeight / totalWeight;
            float wHead = headWeight / totalWeight;

            // Direction calculation
            Vector3 headPos = head.position;
            Vector3 toTarget = (targetLookAtPos - headPos).normalized;
            Vector3 bodyForward = targetGo.transform.forward;
            Vector3 bodyRight = targetGo.transform.right;
            Vector3 bodyUp = targetGo.transform.up;

            float totalAngle = Vector3.Angle(bodyForward, toTarget);
            result.totalTargetAngleDeg = totalAngle;
            result.isTargetBehindCharacter = totalAngle > 90f;

            // Yaw and pitch in character local body frame
            Vector3 projForward = Vector3.ProjectOnPlane(toTarget, bodyUp).normalized;
            float targetYaw = Vector3.SignedAngle(bodyForward, projForward, bodyUp);
            float targetPitch = Vector3.SignedAngle(projForward, toTarget, Vector3.Cross(bodyUp, projForward));

            // Anatomical limits
            float chestMaxYaw = 20f, chestMaxPitch = 15f;
            float neckMaxYaw = 35f, neckMaxPitch = 25f;
            float headMaxYaw = 55f, headMaxPitch = 40f;

            // Compute allocated angles
            float allocChestYaw = Mathf.Clamp(targetYaw * wChest, -chestMaxYaw, chestMaxYaw);
            float allocChestPitch = Mathf.Clamp(targetPitch * wChest, -chestMaxPitch, chestMaxPitch);
            bool chestClamped = Mathf.Abs(allocChestYaw) >= chestMaxYaw || Mathf.Abs(allocChestPitch) >= chestMaxPitch;

            float allocNeckYaw = Mathf.Clamp(targetYaw * wNeck, -neckMaxYaw, neckMaxYaw);
            float allocNeckPitch = Mathf.Clamp(targetPitch * wNeck, -neckMaxPitch, neckMaxPitch);
            bool neckClamped = Mathf.Abs(allocNeckYaw) >= neckMaxYaw || Mathf.Abs(allocNeckPitch) >= neckMaxPitch;

            float allocHeadYaw = Mathf.Clamp(targetYaw * wHead, -headMaxYaw, headMaxYaw);
            float allocHeadPitch = Mathf.Clamp(targetPitch * wHead, -headMaxPitch, headMaxPitch);
            bool headClamped = Mathf.Abs(allocHeadYaw) >= headMaxYaw || Mathf.Abs(allocHeadPitch) >= headMaxPitch;

            result.wasClamped = chestClamped || neckClamped || headClamped;

            var bonesToRotate = new List<(Transform bone, float yaw, float pitch, bool clamped)>();
            if (chest != null) bonesToRotate.Add((chest, allocChestYaw, allocChestPitch, chestClamped));
            if (neck != null) bonesToRotate.Add((neck, allocNeckYaw, allocNeckPitch, neckClamped));
            bonesToRotate.Add((head, allocHeadYaw, allocHeadPitch, headClamped));

            // Save initial rotations
            var initialRotations = new Dictionary<Transform, Quaternion>();
            foreach (var item in bonesToRotate)
            {
                initialRotations[item.bone] = item.bone.localRotation;
            }

            // Apply rotations
            foreach (var item in bonesToRotate)
            {
                Quaternion delta = Quaternion.Euler(item.pitch, item.yaw, 0f);
                item.bone.localRotation = delta * item.bone.localRotation;

                Vector3 euler = item.bone.localEulerAngles;
                Quaternion quat = item.bone.localRotation;
                result.solvedJoints.Add(new NativeGazeJointRotation
                {
                    boneName = item.bone.name,
                    localEuler = new[] { euler.x, euler.y, euler.z },
                    localQuaternion = new[] { quat.x, quat.y, quat.z, quat.w },
                    allocatedYawDeg = item.yaw,
                    allocatedPitchDeg = item.pitch,
                    wasClamped = item.clamped
                });
            }

            // Measure final residual gaze error from head forward
            Vector3 finalGazeForward = head.forward;
            result.residualGazeErrorDeg = Vector3.Angle(finalGazeForward, toTarget);

            // Optional baking
            if (!string.IsNullOrEmpty(bakeToClip) && sampleTime.HasValue)
            {
                string editModeErr = AnimationBackupService.CheckEditMode();
                if (editModeErr != null)
                {
                    result.warnings.Add($"Baking skipped: {editModeErr}");
                }
                else
                {
                    BakeGazeToClip(bakeToClip, targetGo, bonesToRotate, sampleTime.Value, result);
                }
            }

            if (!applyToScene)
            {
                foreach (var item in bonesToRotate)
                {
                    item.bone.localRotation = initialRotations[item.bone];
                }
            }
            else
            {
                var objs = new List<UnityEngine.Object>();
                foreach (var item in bonesToRotate) objs.Add(item.bone);
                Undo.RecordObjects(objs.ToArray(), "Visora: Solve Character Gaze");
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

        private static void BakeGazeToClip(
            string clipPath,
            GameObject targetGo,
            List<(Transform bone, float yaw, float pitch, bool clamped)> bones,
            float time,
            NativeCharacterGazeResult result)
        {
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            if (clip == null)
            {
                result.warnings.Add($"Failed to bake: AnimationClip not found at '{clipPath}'.");
                return;
            }

            try
            {
                string backupId = AnimationBackupService.WriteBackup(clip, clipPath, "character_gaze");
                result.backupId = backupId;

                int undoGroup = Undo.GetCurrentGroup();
                Undo.IncrementCurrentGroup();
                Undo.SetCurrentGroupName("Visora: Bake Character Gaze");
                Undo.RecordObject(clip, "Visora: Bake Character Gaze");

                foreach (var item in bones)
                {
                    string bonePath = GetRelativeHierarchyPath(targetGo.transform, item.bone);
                    string[] props = { "m_LocalRotation.x", "m_LocalRotation.y", "m_LocalRotation.z", "m_LocalRotation.w" };
                    Quaternion rot = item.bone.localRotation;
                    float[] vals = { rot.x, rot.y, rot.z, rot.w };

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
                        if (!replaced) curve.AddKey(time, vals[i]);
                        AnimationUtility.SetEditorCurve(clip, binding, curve);
                    }
                }

                clip.EnsureQuaternionContinuity();
                EditorUtility.SetDirty(clip);
                AssetDatabase.SaveAssets();
                Undo.CollapseUndoOperations(undoGroup);
            }
            catch (Exception ex)
            {
                result.warnings.Add($"Error baking gaze to clip: {ex.Message}");
            }
        }
    }
}
