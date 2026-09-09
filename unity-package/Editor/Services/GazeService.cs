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
            if (chest == null) chest = InverseKinematicsService.FindTransformFuzzy(cached, "Chest", "spine1", "spine2", "spine");

            Transform neck = isHuman ? animator.GetBoneTransform(HumanBodyBones.Neck) : null;
            if (neck == null) neck = InverseKinematicsService.FindTransformFuzzy(cached, "Neck", "neck1");

            Transform head = isHuman ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
            if (head == null) head = InverseKinematicsService.FindTransformFuzzy(cached, "Head");

            Transform leftEye = isHuman ? animator.GetBoneTransform(HumanBodyBones.LeftEye) : null;
            if (leftEye == null) leftEye = InverseKinematicsService.FindTransformFuzzy(cached, "LeftEye", "eye_l", "eye.l");
            Transform rightEye = isHuman ? animator.GetBoneTransform(HumanBodyBones.RightEye) : null;
            if (rightEye == null) rightEye = InverseKinematicsService.FindTransformFuzzy(cached, "RightEye", "eye_r", "eye.r");

            if (head == null)
            {
                result.success = false;
                result.error = "Head transform could not be resolved on target character.";
                return result;
            }

            Vector3 upVector = Vector3.up;
            if (upVectorArray != null && upVectorArray.Length >= 3)
            {
                upVector = new Vector3(upVectorArray[0], upVectorArray[1], upVectorArray[2]);
                if (upVector.sqrMagnitude < 1e-8f)
                {
                    result.success = false;
                    result.error = "upVector must be a non-zero direction.";
                    return result;
                }
                upVector.Normalize();
            }

            chestWeight = Mathf.Max(0f, chestWeight);
            neckWeight = Mathf.Max(0f, neckWeight);
            headWeight = Mathf.Max(0f, headWeight);
            eyesWeight = Mathf.Max(0f, eyesWeight);

            // Transfer missing upstream contributions to the nearest available downstream joint.
            if (chest == null && chestWeight > 0f)
            {
                if (neck != null) neckWeight += chestWeight;
                else headWeight += chestWeight;
                chestWeight = 0f;
                result.warnings.Add("No chest bone found; chest_weight was redistributed downstream.");
            }
            if (neck == null && neckWeight > 0f)
            {
                headWeight += neckWeight;
                neckWeight = 0f;
                result.warnings.Add("No neck bone found; neck_weight was redistributed to the head.");
            }

            bool hasEyes = leftEye != null || rightEye != null;
            float effectiveEyesWeight = eyesWeight;
            if (!hasEyes && eyesWeight > 0.0001f)
            {
                headWeight += eyesWeight;
                effectiveEyesWeight = 0f;
                result.warnings.Add("No eye bones found; eyes_weight was redistributed to the head.");
            }

            // Normalise weights
            float totalWeight = Mathf.Max(0.0001f, chestWeight + neckWeight + headWeight + effectiveEyesWeight);
            float wChest = chestWeight / totalWeight;
            float wNeck = neckWeight / totalWeight;
            float wHead = headWeight / totalWeight;
            float wEyes = effectiveEyesWeight / totalWeight;

            // Direction calculation
            Vector3 headPos = head.position;
            Vector3 headToTarget = targetLookAtPos - headPos;
            if (headToTarget.sqrMagnitude < 1e-8f)
            {
                result.success = false;
                result.error = "Gaze target must not coincide with the head position.";
                return result;
            }
            Vector3 toTarget = headToTarget.normalized;
            Vector3 rawBodyForward = targetGo.transform.forward;
            Vector3 bodyForward = Vector3.ProjectOnPlane(rawBodyForward, upVector);
            if (bodyForward.sqrMagnitude < 1e-8f)
            {
                bodyForward = Vector3.ProjectOnPlane(targetGo.transform.up, upVector);
            }
            if (bodyForward.sqrMagnitude < 1e-8f)
            {
                bodyForward = Vector3.Cross(upVector, Vector3.right);
                if (bodyForward.sqrMagnitude < 1e-8f) bodyForward = Vector3.Cross(upVector, Vector3.forward);
            }
            bodyForward.Normalize();
            Vector3 bodyUp = upVector;
            Vector3 bodyRight = Vector3.Cross(bodyUp, bodyForward).normalized;

            float totalAngle = Vector3.Angle(rawBodyForward, toTarget);
            result.totalTargetAngleDeg = totalAngle;
            result.isTargetBehindCharacter = totalAngle > 90f;

            // Yaw and pitch in character local body frame. When the target is nearly straight above
            // or below the character, the horizontal projection collapses - fall back to a pure
            // pitch about the body-right axis instead of reporting zero rotation.
            Vector3 projForwardRaw = Vector3.ProjectOnPlane(toTarget, bodyUp);
            float targetYaw;
            float targetPitch;
            if (projForwardRaw.sqrMagnitude < 1e-6f)
            {
                targetYaw = 0f;
                targetPitch = Vector3.SignedAngle(bodyForward, toTarget, bodyRight);
            }
            else
            {
                Vector3 projForward = projForwardRaw.normalized;
                targetYaw = Vector3.SignedAngle(bodyForward, projForward, bodyUp);
                targetPitch = Vector3.SignedAngle(projForward, toTarget, Vector3.Cross(bodyUp, projForward));
            }

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

            float eyeMaxYaw = 30f, eyeMaxPitch = 25f;
            bool eyeClamped = false;

            var bonesToRotate = new List<(Transform bone, float yaw, float pitch, bool clamped)>();
            if (chest != null) bonesToRotate.Add((chest, allocChestYaw, allocChestPitch, chestClamped));
            if (neck != null) bonesToRotate.Add((neck, allocNeckYaw, allocNeckPitch, neckClamped));
            bonesToRotate.Add((head, allocHeadYaw, allocHeadPitch, headClamped));
            var eyeBones = new List<Transform>();
            if (wEyes > 0f && leftEye != null) eyeBones.Add(leftEye);
            if (wEyes > 0f && rightEye != null) eyeBones.Add(rightEye);

            // A bake target with no sample time silently no-ops without this guard.
            if (!string.IsNullOrEmpty(bakeToClip) && !sampleTime.HasValue)
            {
                result.success = false;
                result.error = "sample_time is required when bake_to_clip is set.";
                return result;
            }

            // Save initial rotations
            var initialRotations = new Dictionary<Transform, Quaternion>();
            foreach (var item in bonesToRotate)
            {
                initialRotations[item.bone] = item.bone.localRotation;
            }
            foreach (var eye in eyeBones)
            {
                initialRotations[eye] = eye.localRotation;
            }

            try
            {
                // Undo must snapshot the pre-solve pose; recording it after mutation makes undo a no-op.
                if (applyToScene)
                {
                    var undoObjs = new List<UnityEngine.Object>();
                    foreach (var item in bonesToRotate) undoObjs.Add(item.bone);
                    foreach (var eye in eyeBones) undoObjs.Add(eye);
                    Undo.RecordObjects(undoObjs.ToArray(), "Visora: Solve Character Gaze");
                }

                // Apply every body contribution around the requested world-space gaze basis.
                foreach (var item in bonesToRotate)
                {
                    Quaternion yawDelta = Quaternion.AngleAxis(item.yaw, bodyUp);
                    Vector3 pitchAxis = yawDelta * bodyRight;
                    Quaternion pitchDelta = Quaternion.AngleAxis(item.pitch, pitchAxis);
                    item.bone.rotation = pitchDelta * yawDelta * item.bone.rotation;

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

                // Aim each eye from its own position through the residual left by chest/neck/head.
                foreach (var eye in eyeBones)
                {
                    Vector3 eyeTarget = (targetLookAtPos - eye.position).normalized;
                    Vector3 currentHorizontal = Vector3.ProjectOnPlane(eye.forward, bodyUp);
                    if (currentHorizontal.sqrMagnitude < 1e-8f) currentHorizontal = bodyForward;
                    currentHorizontal.Normalize();
                    Vector3 targetHorizontal = Vector3.ProjectOnPlane(eyeTarget, bodyUp);
                    if (targetHorizontal.sqrMagnitude < 1e-8f) targetHorizontal = currentHorizontal;
                    targetHorizontal.Normalize();
                    Vector3 eyeRight = Vector3.Cross(bodyUp, targetHorizontal).normalized;

                    float eyeYaw = Mathf.Clamp(
                        Vector3.SignedAngle(currentHorizontal, targetHorizontal, bodyUp), -eyeMaxYaw, eyeMaxYaw);
                    float eyePitch = Mathf.Clamp(
                        Vector3.SignedAngle(targetHorizontal, eyeTarget, eyeRight), -eyeMaxPitch, eyeMaxPitch);
                    bool thisEyeClamped = Mathf.Abs(eyeYaw) >= eyeMaxYaw || Mathf.Abs(eyePitch) >= eyeMaxPitch;
                    eyeClamped |= thisEyeClamped;

                    Quaternion yawDelta = Quaternion.AngleAxis(eyeYaw, bodyUp);
                    Quaternion pitchDelta = Quaternion.AngleAxis(eyePitch, yawDelta * eyeRight);
                    eye.rotation = pitchDelta * yawDelta * eye.rotation;
                    bonesToRotate.Add((eye, eyeYaw, eyePitch, thisEyeClamped));

                    Vector3 euler = eye.localEulerAngles;
                    Quaternion quat = eye.localRotation;
                    result.solvedJoints.Add(new NativeGazeJointRotation
                    {
                        boneName = eye.name,
                        localEuler = new[] { euler.x, euler.y, euler.z },
                        localQuaternion = new[] { quat.x, quat.y, quat.z, quat.w },
                        allocatedYawDeg = eyeYaw,
                        allocatedPitchDeg = eyePitch,
                        wasClamped = thisEyeClamped
                    });
                }

                result.wasClamped = chestClamped || neckClamped || headClamped || eyeClamped;
                if (eyeBones.Count > 0)
                {
                    Vector3 actualGaze = Vector3.zero;
                    Vector3 desiredGaze = Vector3.zero;
                    foreach (var eye in eyeBones)
                    {
                        actualGaze += eye.forward;
                        desiredGaze += (targetLookAtPos - eye.position).normalized;
                    }
                    result.residualGazeErrorDeg = Vector3.Angle(actualGaze.normalized, desiredGaze.normalized);
                }
                else
                {
                    result.residualGazeErrorDeg = Vector3.Angle(head.forward, toTarget);
                }

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

                if (applyToScene)
                {
                    foreach (var item in bonesToRotate) EditorUtility.SetDirty(item.bone);
                }

                result.success = true;
                return result;
            }
            finally
            {
                if (!applyToScene)
                {
                    foreach (var item in bonesToRotate)
                    {
                        if (item.bone != null && initialRotations.TryGetValue(item.bone, out var rotation))
                        {
                            item.bone.localRotation = rotation;
                        }
                    }
                }
            }
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

            string backupId = null;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "character_gaze");
                result.backupId = backupId;

                int undoGroup = Undo.GetCurrentGroup();
                Undo.IncrementCurrentGroup();
                Undo.SetCurrentGroupName("Visora: Bake Character Gaze");
                Undo.RecordObject(clip, "Visora: Bake Character Gaze");

                foreach (var item in bones)
                {
                    AnimationCurveWriter.WriteQuaternionKey(clip, targetGo.transform, item.bone, time, item.bone.localRotation);
                }

                clip.EnsureQuaternionContinuity();
                EditorUtility.SetDirty(clip);
                AssetDatabase.SaveAssets();
                Undo.CollapseUndoOperations(undoGroup);
            }
            catch (Exception ex)
            {
                result.warnings.Add($"Error baking gaze to clip: {ex.Message}");
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
    }
}
