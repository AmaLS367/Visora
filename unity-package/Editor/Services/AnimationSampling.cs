using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    /// <summary>
    /// Shared AnimationMode sampling helper.
    ///
    /// Mirrors the discipline already used by <see cref="AnimationMotionQAService"/> and
    /// <see cref="AnimationPreviewService"/>: enter animation mode only when it is not already
    /// active, bracket the entire sample loop with a single BeginSampling/EndSampling pair, and
    /// always tear the session down in a finally. Calling AnimationMode.BeginSampling /
    /// SampleAnimationClip without an active animation mode is a no-op (or throws), which silently
    /// bakes the static editor pose - the defect this helper exists to prevent.
    /// </summary>
    internal static class AnimationSampling
    {
        /// <summary>
        /// Samples <paramref name="clip"/> on <paramref name="go"/> at every time in
        /// <paramref name="times"/>, invoking <paramref name="perFrame"/> with the frame index
        /// while the rig is posed at that time. AnimationMode is started/stopped only when it was
        /// not already active on entry.
        /// </summary>
        public static void SampleClip(GameObject go, AnimationClip clip, IReadOnlyList<float> times, Action<int> perFrame)
        {
            if (go == null) throw new ArgumentNullException(nameof(go));
            if (clip == null) throw new ArgumentNullException(nameof(clip));
            if (times == null) throw new ArgumentNullException(nameof(times));
            if (perFrame == null) throw new ArgumentNullException(nameof(perFrame));

            bool wasInAnimationMode = AnimationMode.InAnimationMode();
            try
            {
                if (!wasInAnimationMode) AnimationMode.StartAnimationMode();
                AnimationMode.BeginSampling();

                for (int i = 0; i < times.Count; i++)
                {
                    AnimationMode.SampleAnimationClip(go, clip, times[i]);
                    perFrame(i);
                }
            }
            finally
            {
                AnimationMode.EndSampling();
                if (!wasInAnimationMode) AnimationMode.StopAnimationMode();
            }
        }

        /// <summary>
        /// Builds an evenly spaced, inclusive list of sample times covering [0, clipLength].
        /// The final entry is exactly <paramref name="clipLength"/> so the last frame of the clip
        /// is always sampled (the off-by-one that a bare <c>RoundToInt(length * fps)</c> count misses).
        /// </summary>
        public static List<float> BuildFrameTimes(float clipLength, float fps)
        {
            if (fps <= 0f) fps = 30f;
            float dt = 1f / fps;
            int frameCount = Mathf.Max(2, Mathf.RoundToInt(clipLength * fps) + 1);
            var times = new List<float>(frameCount);
            for (int f = 0; f < frameCount; f++)
            {
                times.Add(Mathf.Min(f * dt, clipLength));
            }
            return times;
        }
    }
}
