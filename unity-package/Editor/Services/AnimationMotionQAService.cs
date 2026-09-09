using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class NativeMotionAnomaly
    {
        public float timestamp;
        public string boneName;
        public string anomalyType; // "jerk_spike", "angular_jerk_spike", "velocity_snap", "arc_kink"
        public string severity; // "critical", "warning"
        public float metricValue;
        public float threshold;
        public string description;
        public string recommendation;
    }

    [Serializable]
    public class NativeBoneMotionSummary
    {
        public string boneName;
        public float peakVelocity;
        public float peakAcceleration;
        public float peakJerk;
        public float averageJerk;
        public float smoothnessScore; // 0.0 to 1.0
    }

    [Serializable]
    public class NativeJointMotionAnalysisResult
    {
        public bool success = true;
        public string error;
        public string clipPath;
        public string targetObjectPath;
        public float clipDuration;
        public int sampleCount;
        public float sampleFps;
        public float overallSmoothnessScore;
        public List<NativeMotionAnomaly> anomalies = new List<NativeMotionAnomaly>();
        public List<NativeBoneMotionSummary> perBoneSummary = new List<NativeBoneMotionSummary>();
        public List<string> recommendations = new List<string>();
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class NativeCurveDiscontinuityItem
    {
        public string curvePath;
        public string propertyName;
        public float timestamp;
        public string issueType; // "quaternion_flip", "euler_wrap", "tangent_spike"
        public string severity; // "critical", "warning"
        public float currentValue;
        public string description;
        public string suggestedFix;
    }

    [Serializable]
    public class NativeCurveDiscontinuityResult
    {
        public bool success = true;
        public string error;
        public string clipPath;
        public int discontinuitiesCount;
        public List<NativeCurveDiscontinuityItem> items = new List<NativeCurveDiscontinuityItem>();
        public bool fixApplied;
        public string backupId;
        public List<string> warnings = new List<string>();
    }

    public static class AnimationMotionQAService
    {
        private static List<Transform> ResolveKeyBones(GameObject rootGo, string[] requestedBones)
        {
            var result = new List<Transform>();
            var cached = rootGo.GetComponentsInChildren<Transform>(true);
            var animator = rootGo.GetComponentInChildren<Animator>();
            bool isHuman = animator != null && animator.avatar != null && animator.avatar.isValid && animator.avatar.isHuman;

            if (requestedBones != null && requestedBones.Length > 0)
            {
                for (int i = 0; i < requestedBones.Length; i++)
                {
                    var t = InverseKinematicsService.FindTransformFuzzy(cached, requestedBones[i]);
                    if (t != null && !result.Contains(t)) result.Add(t);
                }
                return result;
            }

            // Auto-resolve key Humanoid / Rig bones
            if (isHuman)
            {
                HumanBodyBones[] standard = {
                    HumanBodyBones.Hips, HumanBodyBones.Spine, HumanBodyBones.Head,
                    HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot,
                    HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot,
                    HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftHand,
                    HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm, HumanBodyBones.RightHand
                };
                for (int i = 0; i < standard.Length; i++)
                {
                    var b = animator.GetBoneTransform(standard[i]);
                    if (b != null && !result.Contains(b)) result.Add(b);
                }
            }

            if (result.Count == 0)
            {
                string[] patterns = { "pelvis", "hips", "head", "foot_l", "foot_r", "hand_l", "hand_r", "knee_l", "knee_r" };
                for (int i = 0; i < patterns.Length; i++)
                {
                    var t = InverseKinematicsService.FindTransformFuzzy(cached, patterns[i]);
                    if (t != null && !result.Contains(t)) result.Add(t);
                }
            }

            if (result.Count == 0 && cached != null && cached.Length > 0)
            {
                for (int i = 0; i < Mathf.Min(cached.Length, 10); i++)
                {
                    if (cached[i] != rootGo.transform) result.Add(cached[i]);
                }
            }

            return result;
        }

        public static NativeJointMotionAnalysisResult AnalyzeJointMotion(
            string clipPath,
            string targetObjectPath,
            string[] requestedBones,
            int sampleFps,
            float jerkThreshold,
            float angularJerkThreshold)
        {
            var res = new NativeJointMotionAnalysisResult
            {
                clipPath = clipPath,
                targetObjectPath = targetObjectPath,
                sampleFps = sampleFps > 0 ? sampleFps : 60f
            };

            var targetGo = GameObject.Find(targetObjectPath);
            if (targetGo == null)
            {
                res.success = false;
                res.error = $"Target GameObject at '{targetObjectPath}' was not found in scene.";
                return res;
            }

            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            if (clip == null)
            {
                res.success = false;
                res.error = $"AnimationClip not found at path '{clipPath}'.";
                return res;
            }

            float duration = clip.length;
            res.clipDuration = duration;
            float fps = res.sampleFps;
            float dt = 1.0f / fps;
            int sampleCount = Mathf.Max(2, Mathf.CeilToInt(duration * fps) + 1);
            res.sampleCount = sampleCount;

            var bones = ResolveKeyBones(targetGo, requestedBones);
            if (bones.Count == 0)
            {
                res.success = false;
                res.error = "No valid bones or transforms could be resolved for motion analysis.";
                return res;
            }

            // Record samples per bone
            var positions = new Dictionary<Transform, Vector3[]>();
            var rotations = new Dictionary<Transform, Quaternion[]>();
            foreach (var b in bones)
            {
                positions[b] = new Vector3[sampleCount];
                rotations[b] = new Quaternion[sampleCount];
            }

            bool wasInAnimationMode = AnimationMode.InAnimationMode();
            try
            {
                if (!wasInAnimationMode) AnimationMode.StartAnimationMode();
                AnimationMode.BeginSampling();

                for (int i = 0; i < sampleCount; i++)
                {
                    float t = Mathf.Min(i * dt, duration);
                    AnimationMode.SampleAnimationClip(targetGo, clip, t);
                    foreach (var b in bones)
                    {
                        positions[b][i] = b.position;
                        rotations[b][i] = b.rotation;
                    }
                }
            }
            finally
            {
                AnimationMode.EndSampling();
                if (!wasInAnimationMode) AnimationMode.StopAnimationMode();
            }

            float totalSmoothness = 0f;

            // Compute derivatives per bone
            foreach (var b in bones)
            {
                var pos = positions[b];
                var rot = rotations[b];
                float peakVel = 0f, peakAcc = 0f, peakJrk = 0f;
                float sumJrk = 0f;
                int jrkCount = 0;

                var vel = new Vector3[sampleCount - 1];
                var angVel = new float[sampleCount - 1];
                for (int i = 0; i < sampleCount - 1; i++)
                {
                    vel[i] = (pos[i + 1] - pos[i]) / dt;
                    float vMag = vel[i].magnitude;
                    if (vMag > peakVel) peakVel = vMag;
                    angVel[i] = Quaternion.Angle(rot[i], rot[i + 1]) / dt;
                }

                var acc = new Vector3[sampleCount - 2];
                var angAcc = new float[sampleCount - 2];
                for (int i = 0; i < sampleCount - 2; i++)
                {
                    acc[i] = (vel[i + 1] - vel[i]) / dt;
                    float aMag = acc[i].magnitude;
                    if (aMag > peakAcc) peakAcc = aMag;
                    angAcc[i] = (angVel[i + 1] - angVel[i]) / dt;
                }

                for (int i = 0; i < sampleCount - 3; i++)
                {
                    Vector3 jrk = (acc[i + 1] - acc[i]) / dt;
                    float jMag = jrk.magnitude;
                    if (jMag > peakJrk) peakJrk = jMag;
                    sumJrk += jMag;
                    jrkCount++;

                    float angJrk = Mathf.Abs((angAcc[i + 1] - angAcc[i]) / dt);

                    float timestamp = i * dt;

                    // Detect linear jerk spikes
                    if (jMag > jerkThreshold)
                    {
                        res.anomalies.Add(new NativeMotionAnomaly
                        {
                            timestamp = timestamp,
                            boneName = b.name,
                            anomalyType = "jerk_spike",
                            severity = jMag > jerkThreshold * 2f ? "critical" : "warning",
                            metricValue = jMag,
                            threshold = jerkThreshold,
                            description = $"Sudden acceleration change (jerk = {jMag:F1} m/s³) on bone '{b.name}' at t={timestamp:F2}s.",
                            recommendation = $"Smooth or ease tangents around t={timestamp:F2}s to eliminate snapping."
                        });
                    }

                    // Detect angular jerk spikes
                    if (angJrk > angularJerkThreshold)
                    {
                        res.anomalies.Add(new NativeMotionAnomaly
                        {
                            timestamp = timestamp,
                            boneName = b.name,
                            anomalyType = "angular_jerk_spike",
                            severity = angJrk > angularJerkThreshold * 2f ? "critical" : "warning",
                            metricValue = angJrk,
                            threshold = angularJerkThreshold,
                            description = $"Violent rotational pop (angular jerk = {angJrk:F1} deg/s³) on bone '{b.name}' at t={timestamp:F2}s.",
                            recommendation = $"Check for quaternion flips or sharp keyframe tangents on '{b.name}'."
                        });
                    }

                    // Detect velocity snaps (direction reversal without deceleration)
                    if (Vector3.Dot(vel[i], vel[i + 1]) < -0.2f && vel[i].magnitude > 0.4f)
                    {
                        res.anomalies.Add(new NativeMotionAnomaly
                        {
                            timestamp = timestamp,
                            boneName = b.name,
                            anomalyType = "velocity_snap",
                            severity = "warning",
                            metricValue = vel[i].magnitude,
                            threshold = 0.4f,
                            description = $"Abrupt trajectory reversal on bone '{b.name}' at t={timestamp:F2}s without preceding deceleration.",
                            recommendation = "Add anticipation or cushion keyframes across the turning point."
                        });
                    }
                }

                float avgJrk = jrkCount > 0 ? sumJrk / jrkCount : 0f;
                float scoreDenom = Mathf.Max(0.0001f, jerkThreshold * 1.5f);
                float boneScore = Mathf.Clamp01(1f - (avgJrk / scoreDenom));
                totalSmoothness += boneScore;

                res.perBoneSummary.Add(new NativeBoneMotionSummary
                {
                    boneName = b.name,
                    peakVelocity = peakVel,
                    peakAcceleration = peakAcc,
                    peakJerk = peakJrk,
                    averageJerk = avgJrk,
                    smoothnessScore = boneScore
                });
            }

            res.overallSmoothnessScore = bones.Count > 0 ? totalSmoothness / bones.Count : 1.0f;

            if (res.anomalies.Count > 0)
            {
                res.recommendations.Add($"Found {res.anomalies.Count} motion anomalies. Review flagged keyframes and apply tangent easing or run detect_curve_discontinuities.");
            }
            else
            {
                res.recommendations.Add("Motion curves are smooth with zero jerk spikes above threshold.");
            }

            res.success = true;
            return res;
        }

        public static NativeCurveDiscontinuityResult DetectCurveDiscontinuities(
            string clipPath,
            string[] filterCurves,
            bool autoFix)
        {
            var res = new NativeCurveDiscontinuityResult
            {
                clipPath = clipPath,
                fixApplied = false
            };

            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            if (clip == null)
            {
                res.success = false;
                res.error = $"AnimationClip not found at path '{clipPath}'.";
                return res;
            }

            var bindings = AnimationUtility.GetCurveBindings(clip);
            var rotationGroups = new Dictionary<string, (EditorCurveBinding x, EditorCurveBinding y, EditorCurveBinding z, EditorCurveBinding w)>();

            for (int i = 0; i < bindings.Length; i++)
            {
                var b = bindings[i];
                if (filterCurves != null && filterCurves.Length > 0)
                {
                    bool match = false;
                    for (int f = 0; f < filterCurves.Length; f++)
                    {
                        if (b.path.Contains(filterCurves[f], StringComparison.OrdinalIgnoreCase))
                        {
                            match = true;
                            break;
                        }
                    }
                    if (!match) continue;
                }

                if (b.propertyName.StartsWith("m_LocalRotation.", StringComparison.Ordinal))
                {
                    string key = b.path;
                    if (!rotationGroups.TryGetValue(key, out var grp))
                    {
                        grp = (default, default, default, default);
                    }
                    if (b.propertyName == "m_LocalRotation.x") grp.x = b;
                    else if (b.propertyName == "m_LocalRotation.y") grp.y = b;
                    else if (b.propertyName == "m_LocalRotation.z") grp.z = b;
                    else if (b.propertyName == "m_LocalRotation.w") grp.w = b;
                    rotationGroups[key] = grp;
                }

                // Check tangent singularities on any curve
                var curve = AnimationUtility.GetEditorCurve(clip, b);
                if (curve != null)
                {
                    for (int k = 0; k < curve.length; k++)
                    {
                        var keyframe = curve[k];
                        if (float.IsInfinity(keyframe.inTangent) || float.IsInfinity(keyframe.outTangent) ||
                            Mathf.Abs(keyframe.inTangent) > 1000f || Mathf.Abs(keyframe.outTangent) > 1000f)
                        {
                            res.items.Add(new NativeCurveDiscontinuityItem
                            {
                                curvePath = b.path,
                                propertyName = b.propertyName,
                                timestamp = keyframe.time,
                                issueType = "tangent_spike",
                                severity = "warning",
                                currentValue = keyframe.value,
                                description = $"Extreme tangent slope (in={keyframe.inTangent:F1}, out={keyframe.outTangent:F1}) at t={keyframe.time:F2}s on '{b.path}'.",
                                suggestedFix = "Flatten or smooth tangents to eliminate keyframe overshoot."
                            });
                        }
                    }
                }
            }

            // Check quaternion antipodal sign flips
            foreach (var kvp in rotationGroups)
            {
                var grp = kvp.Value;
                if (string.IsNullOrEmpty(grp.x.propertyName) || string.IsNullOrEmpty(grp.y.propertyName) ||
                    string.IsNullOrEmpty(grp.z.propertyName) || string.IsNullOrEmpty(grp.w.propertyName))
                    continue;

                var cx = AnimationUtility.GetEditorCurve(clip, grp.x);
                var cy = AnimationUtility.GetEditorCurve(clip, grp.y);
                var cz = AnimationUtility.GetEditorCurve(clip, grp.z);
                var cw = AnimationUtility.GetEditorCurve(clip, grp.w);

                if (cx == null || cy == null || cz == null || cw == null) continue;

                // The four component curves may have different key counts / times (partial edits,
                // curve simplification), so sample them on the union of all key times rather than
                // indexing cy/cz/cw with cx's key index.
                var sampleTimes = new SortedSet<float>();
                foreach (var curve in new[] { cx, cy, cz, cw })
                {
                    for (int k = 0; k < curve.length; k++) sampleTimes.Add(curve[k].time);
                }
                if (sampleTimes.Count < 2) continue;

                var timeList = new List<float>(sampleTimes);
                for (int k = 0; k < timeList.Count - 1; k++)
                {
                    float t0 = timeList[k];
                    float t1 = timeList[k + 1];
                    Quaternion q0 = new Quaternion(cx.Evaluate(t0), cy.Evaluate(t0), cz.Evaluate(t0), cw.Evaluate(t0));
                    Quaternion q1 = new Quaternion(cx.Evaluate(t1), cy.Evaluate(t1), cz.Evaluate(t1), cw.Evaluate(t1));

                    float dot = (q0.x * q1.x) + (q0.y * q1.y) + (q0.z * q1.z) + (q0.w * q1.w);
                    if (dot < -0.0001f)
                    {
                        res.items.Add(new NativeCurveDiscontinuityItem
                        {
                            curvePath = kvp.Key,
                            propertyName = "m_LocalRotation",
                            timestamp = t1,
                            issueType = "quaternion_flip",
                            severity = "critical",
                            currentValue = dot,
                            description = $"Quaternion sign flip (dot={dot:F2} < 0) between t={t0:F2}s and t={t1:F2}s on bone '{kvp.Key}', causing 360° flip.",
                            suggestedFix = "Run EnsureQuaternionContinuity or negate subsequent key."
                        });
                    }
                }
            }

            res.discontinuitiesCount = res.items.Count;

            // Optional auto-fix
            if (autoFix && res.discontinuitiesCount > 0)
            {
                string editModeErr = AnimationBackupService.CheckEditMode();
                if (editModeErr != null)
                {
                    res.warnings.Add($"Auto-fix skipped: {editModeErr}");
                }
                else
                {
                    try
                    {
                        string backupId = AnimationBackupService.WriteBackup(clip, clipPath, "fix_discontinuities");
                        res.backupId = backupId;

                        int undoGroup = Undo.GetCurrentGroup();
                        Undo.IncrementCurrentGroup();
                        Undo.SetCurrentGroupName("Visora: Fix Curve Discontinuities");
                        Undo.RecordObject(clip, "Visora: Fix Curve Discontinuities");

                        clip.EnsureQuaternionContinuity();
                        EditorUtility.SetDirty(clip);
                        AssetDatabase.SaveAssets();
                        Undo.CollapseUndoOperations(undoGroup);

                        res.fixApplied = true;
                    }
                    catch (Exception ex)
                    {
                        res.warnings.Add($"Auto-fix error: {ex.Message}");
                    }
                }
            }

            res.success = true;
            return res;
        }
    }
}
