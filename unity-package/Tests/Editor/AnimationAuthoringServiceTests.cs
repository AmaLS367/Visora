using System;
using NUnit.Framework;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class AnimationAuthoringServiceTests
    {
        [Test]
        public void ResolveComponentType_ResolvesTransformWithoutSearching()
        {
            Assert.That(AnimationAuthoringService.ResolveComponentType("Transform"), Is.EqualTo(typeof(Transform)));
        }

        [Test]
        public void ResolveComponentType_ResolvesAWellKnownComponentByName()
        {
            Assert.That(AnimationAuthoringService.ResolveComponentType("Light"), Is.EqualTo(typeof(Light)));
        }

        [Test]
        public void ResolveComponentType_ThrowsOnUnknownName()
        {
            Assert.Throws<ArgumentException>(() => AnimationAuthoringService.ResolveComponentType("NotARealComponent"));
        }

        [Test]
        public void FindKeyIndexNearTime_MatchesWithinHalfAFrame()
        {
            var curve = new AnimationCurve(new Keyframe(0f, 0f), new Keyframe(1f, 1f));
            // 24fps -> tolerance ~0.0208s; 1.01 is inside it, 1.05 is not.
            Assert.That(AnimationAuthoringService.FindKeyIndexNearTime(curve, 1.01f, 24f), Is.EqualTo(1));
            Assert.That(AnimationAuthoringService.FindKeyIndexNearTime(curve, 1.05f, 24f), Is.EqualTo(-1));
        }

        [Test]
        public void FindKeyIndexNearTime_FloorsToleranceOnDegenerateFrameRate()
        {
            var curve = new AnimationCurve(new Keyframe(0f, 0f));
            Assert.DoesNotThrow(() => AnimationAuthoringService.FindKeyIndexNearTime(curve, 0f, 0f));
        }

        [Test]
        public void ResolveChannels_ReturnsExistingQuaternionChannelsInCanonicalOrder()
        {
            var clip = new AnimationClip();
            var go = new GameObject("Probe");
            try
            {
                var curve = new AnimationCurve(new Keyframe(0f, 0f));
                // Bind in a deliberately scrambled order to prove the result is re-ordered, not
                // just echoed back as found.
                clip.SetCurve("", typeof(Transform), "m_LocalRotation.w", curve);
                clip.SetCurve("", typeof(Transform), "m_LocalRotation.z", curve);
                clip.SetCurve("", typeof(Transform), "m_LocalRotation.x", curve);
                clip.SetCurve("", typeof(Transform), "m_LocalRotation.y", curve);

                var channels = AnimationAuthoringService.ResolveChannels(
                    clip, "", typeof(Transform), "m_LocalRotation", go, out bool curveExisted);

                Assert.That(curveExisted, Is.True);
                Assert.That(channels, Is.EqualTo(new[]
                {
                    "m_LocalRotation.x", "m_LocalRotation.y", "m_LocalRotation.z", "m_LocalRotation.w",
                }));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(go);
                UnityEngine.Object.DestroyImmediate(clip);
            }
        }

        [Test]
        public void ResolveChannels_NewVectorPropertyUsesWellKnownTable()
        {
            var clip = new AnimationClip();
            try
            {
                var channels = AnimationAuthoringService.ResolveChannels(
                    clip, "", typeof(Transform), "m_LocalPosition", null, out bool curveExisted);

                Assert.That(curveExisted, Is.False);
                Assert.That(channels, Is.EqualTo(new[] { "m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z" }));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(clip);
            }
        }

        [Test]
        public void ResolveChannels_NewSerializedFloatPropertyResolvesViaLiveInstance()
        {
            var clip = new AnimationClip();
            var go = new GameObject("LightProbe");
            try
            {
                var light = go.AddComponent<Light>();

                // The public C# property is "intensity"; the serialized/animatable binding is
                // "m_Intensity". This is exactly the mismatch reflection on Light's public API
                // cannot resolve — proving the SerializedObject path is actually exercised.
                var channels = AnimationAuthoringService.ResolveChannels(
                    clip, "LightProbe", typeof(Light), "m_Intensity", go, out bool curveExisted);

                Assert.That(curveExisted, Is.False);
                Assert.That(channels, Is.EqualTo(new[] { "m_Intensity" }));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(go);
                UnityEngine.Object.DestroyImmediate(clip);
            }
        }

        [Test]
        public void ResolveChannels_ThrowsWhenNoLiveInstanceAndNotInWellKnownTable()
        {
            var clip = new AnimationClip();
            try
            {
                Assert.Throws<ArgumentException>(() => AnimationAuthoringService.ResolveChannels(
                    clip, "Missing", typeof(Light), "m_Intensity", null, out _));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(clip);
            }
        }
    }
}
