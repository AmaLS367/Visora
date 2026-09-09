using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    /// <summary>
    /// Shared writer for <c>m_LocalRotation.{x,y,z,w}</c> quaternion curves on an AnimationClip.
    ///
    /// Every caller upserts keyframes by time and leaves keys outside the touched times intact -
    /// it never calls <c>AnimationClip.SetCurve</c>, which replaces the whole channel and would
    /// discard the clip's existing rotation animation outside the edited window.
    /// </summary>
    internal static class AnimationCurveWriter
    {
        private static readonly string[] QuaternionProps =
        {
            "m_LocalRotation.x", "m_LocalRotation.y", "m_LocalRotation.z", "m_LocalRotation.w"
        };

        /// <summary>
        /// Upserts the given (time, local rotation) samples into the four quaternion channels of
        /// <paramref name="bone"/> (path resolved relative to <paramref name="rootTransform"/>),
        /// preserving every existing key at a different time.
        /// </summary>
        public static void WriteQuaternionCurves(
            AnimationClip clip,
            Transform rootTransform,
            Transform bone,
            IReadOnlyList<(float time, Quaternion rotation)> samples,
            float? windowStart = null,
            float? windowEnd = null)
        {
            if (clip == null) throw new ArgumentNullException(nameof(clip));
            if (bone == null) throw new ArgumentNullException(nameof(bone));
            if (samples == null || samples.Count == 0) return;

            string bonePath = AnimationUtility.CalculateTransformPath(bone, rootTransform);

            for (int axis = 0; axis < 4; axis++)
            {
                var binding = EditorCurveBinding.FloatCurve(bonePath, typeof(Transform), QuaternionProps[axis]);
                var curve = AnimationUtility.GetEditorCurve(clip, binding) ?? new AnimationCurve();

                if (windowStart.HasValue && windowEnd.HasValue)
                {
                    // The contact window is replaced by solved samples. Retaining an unrelated
                    // off-grid source key inside it would pull the evaluated curve away from the
                    // contact, while keys at and outside the boundaries carry the outer segment's
                    // tangent metadata and must remain available to UpsertKey below.
                    for (int k = curve.length - 1; k >= 0; k--)
                    {
                        float existingTime = curve[k].time;
                        if (existingTime > windowStart.Value + 0.0001f
                            && existingTime < windowEnd.Value - 0.0001f)
                        {
                            curve.RemoveKey(k);
                        }
                    }
                }

                for (int s = 0; s < samples.Count; s++)
                {
                    float time = samples[s].time;
                    Quaternion q = samples[s].rotation;
                    float value = Component(q, axis);
                    float tangent = SampleTangent(samples, s, axis);
                    bool preserveAllTangents = samples.Count == 1 && !windowStart.HasValue && !windowEnd.HasValue;
                    bool preserveIncoming = windowStart.HasValue && Mathf.Abs(time - windowStart.Value) < 0.0001f;
                    bool preserveOutgoing = windowEnd.HasValue && Mathf.Abs(time - windowEnd.Value) < 0.0001f;
                    UpsertKey(
                        curve, time, value, tangent, preserveAllTangents, preserveIncoming, preserveOutgoing);
                }

                AnimationUtility.SetEditorCurve(clip, binding, curve);
            }
        }

        /// <summary>Convenience overload for a single keyframe (IK / gaze single-pose bake).</summary>
        public static void WriteQuaternionKey(
            AnimationClip clip,
            Transform rootTransform,
            Transform bone,
            float time,
            Quaternion localRotation)
        {
            WriteQuaternionCurves(clip, rootTransform, bone, new[] { (time, localRotation) });
        }

        private static float Component(Quaternion rotation, int axis)
        {
            return axis switch
            {
                0 => rotation.x,
                1 => rotation.y,
                2 => rotation.z,
                _ => rotation.w,
            };
        }

        private static float SampleTangent(
            IReadOnlyList<(float time, Quaternion rotation)> samples,
            int index,
            int axis)
        {
            if (samples.Count < 2) return 0f;
            int previous = Mathf.Max(0, index - 1);
            int next = Mathf.Min(samples.Count - 1, index + 1);
            float deltaTime = samples[next].time - samples[previous].time;
            if (Mathf.Abs(deltaTime) < 1e-6f) return 0f;
            return (Component(samples[next].rotation, axis) - Component(samples[previous].rotation, axis)) / deltaTime;
        }

        private static void UpsertKey(
            AnimationCurve curve,
            float time,
            float value,
            float tangent,
            bool preserveAllTangents,
            bool preserveIncoming,
            bool preserveOutgoing)
        {
            for (int k = 0; k < curve.length; k++)
            {
                if (Mathf.Abs(curve[k].time - time) < 0.0001f)
                {
                    Keyframe previous = curve[k];
                    var replacement = new Keyframe(time, value, tangent, tangent);
                    if (preserveAllTangents || preserveIncoming)
                    {
                        replacement.inTangent = previous.inTangent;
                        replacement.inWeight = previous.inWeight;
                    }
                    if (preserveAllTangents || preserveOutgoing)
                    {
                        replacement.outTangent = previous.outTangent;
                        replacement.outWeight = previous.outWeight;
                    }

                    WeightedMode weightedMode = WeightedMode.None;
                    if ((preserveAllTangents || preserveIncoming)
                        && (previous.weightedMode & WeightedMode.In) != 0)
                    {
                        weightedMode |= WeightedMode.In;
                    }
                    if ((preserveAllTangents || preserveOutgoing)
                        && (previous.weightedMode & WeightedMode.Out) != 0)
                    {
                        weightedMode |= WeightedMode.Out;
                    }
                    replacement.weightedMode = weightedMode;
                    curve.MoveKey(k, replacement);
                    return;
                }
            }
            curve.AddKey(new Keyframe(time, value, tangent, tangent));
        }
    }
}
