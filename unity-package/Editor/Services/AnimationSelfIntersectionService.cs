using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class BodyPenetrationEvent
    {
        public float time;
        public string limbA;
        public string limbB;
        public float penetrationDepthMeters;
        public string severity; // "critical", "warning"
        public string description;
    }

    [Serializable]
    public class SelfIntersectionRequest
    {
        public string targetObjectPath;
        public string clipPath;
        public int sampleFps = 30;
        public float toleranceMeters = 0.02f;
    }

    [Serializable]
    public class SelfIntersectionResult
    {
        public bool success = true;
        public string error;
        public string targetObjectPath;
        public string clipPath;
        public int intersectionsFound;
        public int sampleCount;
        public float cleanIntervalPercent;
        public float maxPenetrationDepth;
        public List<BodyPenetrationEvent> penetrations = new List<BodyPenetrationEvent>();
        public List<string> warnings = new List<string>();
    }

    internal class BodySegmentProxy
    {
        public string name;
        public Transform start;
        public Transform end;
        public float radius;
    }

    /// <summary>
    /// Diagnoses character mesh self-intersections and limb-body clipping across AnimationClip playback
    /// using skeletal capsule proxies.
    /// </summary>
    public static class AnimationSelfIntersectionService
    {
        public static SelfIntersectionResult AnalyzeSelfIntersections(SelfIntersectionRequest request)
        {
            var result = new SelfIntersectionResult
            {
                targetObjectPath = request?.targetObjectPath,
                clipPath = request?.clipPath
            };

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
                result.error = $"Target GameObject '{request.targetObjectPath}' not found.";
                return result;
            }

            var clip = AnimationPreviewService.ResolveClip(request.clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip '{request.clipPath}' not found.";
                return result;
            }

            var segments = BuildSegmentProxies(rootGo);
            if (segments.Count < 2)
            {
                result.success = true;
                result.cleanIntervalPercent = 100f;
                result.warnings.Add("Insufficient humanoid or named bones identified to build body collision proxies.");
                return result;
            }

            // Define non-adjacent collision pairs
            var pairs = BuildCollisionPairs(segments);

            // Snapshot rest transforms
            var allTransforms = rootGo.GetComponentsInChildren<Transform>(true);
            var restPos = new Vector3[allTransforms.Length];
            var restRot = new Quaternion[allTransforms.Length];
            for (int i = 0; i < allTransforms.Length; i++)
            {
                restPos[i] = allTransforms[i].localPosition;
                restRot[i] = allTransforms[i].localRotation;
            }

            float fps = request.sampleFps > 0 ? request.sampleFps : 30f;
            float dt = 1f / fps;
            int totalFrames = Mathf.Max(2, Mathf.RoundToInt(clip.length * fps));
            result.sampleCount = totalFrames;

            int framesWithPenetration = 0;
            float maxPenetration = 0f;

            try
            {
                for (int f = 0; f < totalFrames; f++)
                {
                    float t = Mathf.Clamp(f * dt, 0f, clip.length);

                    AnimationMode.BeginSampling();
                    AnimationMode.SampleAnimationClip(rootGo, clip, t);
                    AnimationMode.EndSampling();

                    bool framePenetrated = false;

                    for (int p = 0; p < pairs.Count; p++)
                    {
                        var segA = pairs[p].Item1;
                        var segB = pairs[p].Item2;

                        float dist = SegmentSegmentDistance(
                            segA.start.position, segA.end.position,
                            segB.start.position, segB.end.position);

                        float combinedRadius = segA.radius + segB.radius;
                        float penetration = combinedRadius - dist;

                        if (penetration > request.toleranceMeters)
                        {
                            framePenetrated = true;
                            if (penetration > maxPenetration) maxPenetration = penetration;

                            // Limit reported events to prevent payload explosion
                            if (result.penetrations.Count < 50)
                            {
                                string severity = penetration > 0.05f ? "critical" : "warning";
                                result.penetrations.Add(new BodyPenetrationEvent
                                {
                                    time = (float)Math.Round(t, 3),
                                    limbA = segA.name,
                                    limbB = segB.name,
                                    penetrationDepthMeters = (float)Math.Round(penetration, 4),
                                    severity = severity,
                                    description = $"{segA.name} penetrates {segB.name} by {penetration * 100f:F1}cm at t={t:F2}s ({severity})."
                                });
                            }
                        }
                    }

                    if (framePenetrated) framesWithPenetration++;
                }
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

            result.success = true;
            result.intersectionsFound = result.penetrations.Count;
            result.maxPenetrationDepth = (float)Math.Round(maxPenetration, 4);
            result.cleanIntervalPercent = totalFrames > 0
                ? (float)Math.Round(((totalFrames - framesWithPenetration) / (float)totalFrames) * 100f, 1)
                : 100f;

            return result;
        }

        private static List<BodySegmentProxy> BuildSegmentProxies(GameObject rootGo)
        {
            var segments = new List<BodySegmentProxy>();
            var animator = rootGo.GetComponentInChildren<Animator>();
            bool isHuman = animator != null && animator.avatar != null && animator.avatar.isValid && animator.avatar.isHuman;
            Transform[] cached = rootGo.GetComponentsInChildren<Transform>(true);

            Transform hips = isHuman ? animator.GetBoneTransform(HumanBodyBones.Hips) : InverseKinematicsService.FindTransformFuzzy(cached, "Hips", "Pelvis");
            Transform spine = isHuman ? animator.GetBoneTransform(HumanBodyBones.Spine) : InverseKinematicsService.FindTransformFuzzy(cached, "Spine", "Spine1");
            Transform chest = isHuman ? animator.GetBoneTransform(HumanBodyBones.Chest) : InverseKinematicsService.FindTransformFuzzy(cached, "Chest", "Spine2");

            Transform lUpperArm = isHuman ? animator.GetBoneTransform(HumanBodyBones.LeftUpperArm) : InverseKinematicsService.FindTransformFuzzy(cached, "LeftUpperArm", "upperarm_l");
            Transform lForearm = isHuman ? animator.GetBoneTransform(HumanBodyBones.LeftLowerArm) : InverseKinematicsService.FindTransformFuzzy(cached, "LeftLowerArm", "forearm_l");
            Transform lHand = isHuman ? animator.GetBoneTransform(HumanBodyBones.LeftHand) : InverseKinematicsService.FindTransformFuzzy(cached, "LeftHand", "hand_l");

            Transform rUpperArm = isHuman ? animator.GetBoneTransform(HumanBodyBones.RightUpperArm) : InverseKinematicsService.FindTransformFuzzy(cached, "RightUpperArm", "upperarm_r");
            Transform rForearm = isHuman ? animator.GetBoneTransform(HumanBodyBones.RightLowerArm) : InverseKinematicsService.FindTransformFuzzy(cached, "RightLowerArm", "forearm_r");
            Transform rHand = isHuman ? animator.GetBoneTransform(HumanBodyBones.RightHand) : InverseKinematicsService.FindTransformFuzzy(cached, "RightHand", "hand_r");

            Transform lThigh = isHuman ? animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg) : InverseKinematicsService.FindTransformFuzzy(cached, "LeftUpperLeg", "thigh_l");
            Transform lCalf = isHuman ? animator.GetBoneTransform(HumanBodyBones.LeftLowerLeg) : InverseKinematicsService.FindTransformFuzzy(cached, "LeftLowerLeg", "calf_l");

            Transform rThigh = isHuman ? animator.GetBoneTransform(HumanBodyBones.RightUpperLeg) : InverseKinematicsService.FindTransformFuzzy(cached, "RightUpperLeg", "thigh_r");
            Transform rCalf = isHuman ? animator.GetBoneTransform(HumanBodyBones.RightLowerLeg) : InverseKinematicsService.FindTransformFuzzy(cached, "RightLowerLeg", "calf_r");

            if (hips != null && spine != null) segments.Add(new BodySegmentProxy { name = "Pelvis", start = hips, end = spine, radius = 0.14f });
            if (spine != null && chest != null) segments.Add(new BodySegmentProxy { name = "Torso", start = spine, end = chest, radius = 0.15f });

            if (lUpperArm != null && lForearm != null) segments.Add(new BodySegmentProxy { name = "LeftUpperArm", start = lUpperArm, end = lForearm, radius = 0.08f });
            if (lForearm != null && lHand != null) segments.Add(new BodySegmentProxy { name = "LeftForearm", start = lForearm, end = lHand, radius = 0.06f });

            if (rUpperArm != null && rForearm != null) segments.Add(new BodySegmentProxy { name = "RightUpperArm", start = rUpperArm, end = rForearm, radius = 0.08f });
            if (rForearm != null && rHand != null) segments.Add(new BodySegmentProxy { name = "RightForearm", start = rForearm, end = rHand, radius = 0.06f });

            if (lThigh != null && lCalf != null) segments.Add(new BodySegmentProxy { name = "LeftThigh", start = lThigh, end = lCalf, radius = 0.11f });
            if (rThigh != null && rCalf != null) segments.Add(new BodySegmentProxy { name = "RightThigh", start = rThigh, end = rCalf, radius = 0.11f });

            return segments;
        }

        private static List<Tuple<BodySegmentProxy, BodySegmentProxy>> BuildCollisionPairs(List<BodySegmentProxy> segments)
        {
            var dict = new Dictionary<string, BodySegmentProxy>(StringComparer.OrdinalIgnoreCase);
            foreach (var s in segments) dict[s.name] = s;

            var pairs = new List<Tuple<BodySegmentProxy, BodySegmentProxy>>();

            void TryAddPair(string a, string b)
            {
                if (dict.TryGetValue(a, out var sa) && dict.TryGetValue(b, out var sb))
                {
                    pairs.Add(new Tuple<BodySegmentProxy, BodySegmentProxy>(sa, sb));
                }
            }

            TryAddPair("LeftForearm", "Torso");
            TryAddPair("RightForearm", "Torso");
            TryAddPair("LeftForearm", "Pelvis");
            TryAddPair("RightForearm", "Pelvis");
            TryAddPair("LeftForearm", "RightForearm");
            TryAddPair("LeftThigh", "RightThigh");
            TryAddPair("LeftForearm", "LeftThigh");
            TryAddPair("RightForearm", "RightThigh");

            return pairs;
        }

        private static float SegmentSegmentDistance(Vector3 p1, Vector3 p2, Vector3 q1, Vector3 q2)
        {
            Vector3 u = p2 - p1;
            Vector3 v = q2 - q1;
            Vector3 w = p1 - q1;

            float a = Vector3.Dot(u, u);
            float b = Vector3.Dot(u, v);
            float c = Vector3.Dot(v, v);
            float d = Vector3.Dot(u, w);
            float e = Vector3.Dot(v, w);
            float D = (a * c) - (b * b);

            float sc, sN, sD = D;
            float tc, tN, tD = D;

            if (D < 0.0001f)
            {
                sN = 0.0f;
                sD = 1.0f;
                tN = e;
                tD = c;
            }
            else
            {
                sN = (b * e) - (c * d);
                tN = (a * e) - (b * d);
                if (sN < 0.0f)
                {
                    sN = 0.0f;
                    tN = e;
                    tD = c;
                }
                else if (sN > sD)
                {
                    sN = sD;
                    tN = e + b;
                    tD = c;
                }
            }

            if (tN < 0.0f)
            {
                tN = 0.0f;
                if (-d < 0.0f) sN = 0.0f;
                else if (-d > a) sN = sD;
                else
                {
                    sN = -d;
                    sD = a;
                }
            }
            else if (tN > tD)
            {
                tN = tD;
                if ((-d + b) < 0.0f) sN = 0.0f;
                else if ((-d + b) > a) sN = sD;
                else
                {
                    sN = -d + b;
                    sD = a;
                }
            }

            sc = Mathf.Abs(sN) < 0.0001f ? 0.0f : sN / sD;
            tc = Mathf.Abs(tN) < 0.0001f ? 0.0f : tN / tD;

            Vector3 dP = w + (sc * u) - (tc * v);
            return dP.magnitude;
        }
    }
}
