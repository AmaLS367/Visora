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
    /// using skeletal capsule proxies built generically from the rig hierarchy (no humanoid assumption).
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
                // No fake "100% clean" pass on a rig the analyzer cannot model.
                result.success = false;
                result.error = "Cannot build at least 2 skeletal capsule proxies for this rig; " +
                               "self-intersection analysis is not available for it.";
                return result;
            }

            var pairs = BuildCollisionPairs(segments);
            if (pairs.Count == 0)
            {
                result.success = false;
                result.error = "No non-adjacent segment pairs to test on this rig.";
                return result;
            }

            // Snapshot rest transforms (restored in finally; also covers an already-active animation mode).
            var allTransforms = rootGo.GetComponentsInChildren<Transform>(true);
            var restPos = new Vector3[allTransforms.Length];
            var restRot = new Quaternion[allTransforms.Length];
            for (int i = 0; i < allTransforms.Length; i++)
            {
                restPos[i] = allTransforms[i].localPosition;
                restRot[i] = allTransforms[i].localRotation;
            }

            float fps = request.sampleFps > 0 ? request.sampleFps : 30f;
            var times = AnimationSampling.BuildFrameTimes(clip.length, fps);
            result.sampleCount = times.Count;

            int framesWithPenetration = 0;
            float maxPenetration = 0f;

            try
            {
                AnimationSampling.SampleClip(rootGo, clip, times, i =>
                {
                    float t = times[i];
                    bool framePenetrated = false;

                    for (int p = 0; p < pairs.Count; p++)
                    {
                        var segA = pairs[p].Item1;
                        var segB = pairs[p].Item2;

                        Vector3 a0 = segA.start.position, a1 = segA.end.position;
                        Vector3 b0 = segB.start.position, b1 = segB.end.position;

                        // Broad phase: bounding-sphere reject before the precise capsule test.
                        Vector3 ca = (a0 + a1) * 0.5f, cb = (b0 + b1) * 0.5f;
                        float ra = (Vector3.Distance(a0, a1) * 0.5f) + segA.radius;
                        float rb = (Vector3.Distance(b0, b1) * 0.5f) + segB.radius;
                        if ((ca - cb).sqrMagnitude > (ra + rb) * (ra + rb)) continue;

                        float dist = SegmentSegmentDistance(a0, a1, b0, b1);

                        float penetration = (segA.radius + segB.radius) - dist;
                        if (penetration > request.toleranceMeters)
                        {
                            framePenetrated = true;
                            if (penetration > maxPenetration) maxPenetration = penetration;

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
                });
            }
            finally
            {
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
            result.cleanIntervalPercent = times.Count > 0
                ? (float)Math.Round(((times.Count - framesWithPenetration) / (float)times.Count) * 100f, 1)
                : 100f;

            return result;
        }

        // Bones whose name matches any of these are twist / helper / IK / rig-root markers - not body mass.
        private static readonly string[] HelperBoneMarkers =
        {
            "twist", "_end", "end_", "roll", "ik_", "_ik", "pole", "target", "adjust", "helper",
            "ctrl", "_aux", "bendy", "ribbon", "armature", "rootjoint", "_root", "root_",
            "reference", "master", "prop"
        };

        // Cap on segment count so a high-density rig (500+ twist bones) does not blow up the O(n^2)
        // pair set - keep the longest links, which carry the body mass.
        private const int MaxSegments = 48;

        /// <summary>
        /// Builds capsule proxies from bone-to-child-bone links. Bone transforms come from every
        /// SkinnedMeshRenderer's bone array (union), falling back to the full transform hierarchy
        /// when the rig has no skinned mesh. Twist/helper bones are filtered out and the set is
        /// capped to the longest <see cref="MaxSegments"/> links. Radius scales with segment length.
        /// </summary>
        private static List<BodySegmentProxy> BuildSegmentProxies(GameObject rootGo)
        {
            var boneSet = new HashSet<Transform>();
            foreach (var smr in rootGo.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (smr.bones == null) continue;
                foreach (var b in smr.bones)
                {
                    if (b != null) boneSet.Add(b);
                }
            }
            if (boneSet.Count < 2)
            {
                boneSet.Clear();
                foreach (var t in rootGo.GetComponentsInChildren<Transform>(true)) boneSet.Add(t);
            }

            var segments = new List<BodySegmentProxy>();
            foreach (var bone in boneSet)
            {
                if (IsHelperBone(bone.name)) continue;

                for (int i = 0; i < bone.childCount; i++)
                {
                    Transform child = bone.GetChild(i);
                    if (!boneSet.Contains(child) || IsHelperBone(child.name)) continue;

                    float length = Vector3.Distance(bone.position, child.position);
                    if (length < 0.04f) continue; // skip near-zero links

                    segments.Add(new BodySegmentProxy
                    {
                        name = bone.name,
                        start = bone,
                        end = child,
                        radius = Mathf.Clamp(length * 0.15f, 0.02f, 0.09f)
                    });
                }
            }

            if (segments.Count == 0) return segments;

            segments.Sort((x, y) =>
                Vector3.Distance(y.start.position, y.end.position)
                    .CompareTo(Vector3.Distance(x.start.position, x.end.position)));

            // Drop torso-spanning outlier links (a rig-root -> hip bone dwarfs real limb segments and
            // would "penetrate" everything). Anything longer than 2.5x the median limb length goes.
            float median = Vector3.Distance(
                segments[segments.Count / 2].start.position, segments[segments.Count / 2].end.position);
            if (median > 1e-4f)
            {
                segments.RemoveAll(s => Vector3.Distance(s.start.position, s.end.position) > median * 2.5f);
            }

            if (segments.Count > MaxSegments)
            {
                segments.RemoveRange(MaxSegments, segments.Count - MaxSegments);
            }

            return segments;
        }

        private static bool IsHelperBone(string name)
        {
            string n = name.ToLowerInvariant();
            for (int i = 0; i < HelperBoneMarkers.Length; i++)
            {
                if (n.Contains(HelperBoneMarkers[i])) return true;
            }
            return false;
        }

        /// <summary>
        /// All segment pairs except those that share a joint (chained bones) or whose start bones are
        /// in a direct parent-child relationship - those always "touch" and would be false positives.
        /// </summary>
        private static List<Tuple<BodySegmentProxy, BodySegmentProxy>> BuildCollisionPairs(List<BodySegmentProxy> segments)
        {
            var pairs = new List<Tuple<BodySegmentProxy, BodySegmentProxy>>();
            for (int i = 0; i < segments.Count; i++)
            {
                for (int j = i + 1; j < segments.Count; j++)
                {
                    var a = segments[i];
                    var b = segments[j];

                    bool chained = a.end == b.start || b.end == a.start || a.start == b.start || a.end == b.end;
                    bool parentChild = a.start.parent == b.start || b.start.parent == a.start;
                    if (chained || parentChild) continue;

                    pairs.Add(new Tuple<BodySegmentProxy, BodySegmentProxy>(a, b));
                }
            }
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
