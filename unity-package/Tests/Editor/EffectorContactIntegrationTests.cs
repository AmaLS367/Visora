using System.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class EffectorContactIntegrationTests : AnimationIntegrationTestBase
    {
        private static Keyframe WeightedKey(float time, float value, float inTangent, float outTangent)
        {
            var key = new Keyframe(time, value)
            {
                inTangent = inTangent,
                outTangent = outTangent,
                inWeight = 0.2f,
                outWeight = 0.3f,
                weightedMode = WeightedMode.Both,
            };
            return key;
        }

        private static Keyframe KeyAt(AnimationCurve curve, float time)
        {
            return curve.keys.Single(key => Mathf.Abs(key.time - time) < 0.0001f);
        }

        private (GameObject root, Transform upper, Transform lower, Transform end, AnimationClip clip) CreateContactFixture(
            string clipName)
        {
            var chain = CreateLegChain($"Contact{clipName}", Vector3.zero);
            Track(chain.root);
            var clip = CreateClip(clipName);
            string upperPath = chain.upper.name;
            string lowerPath = $"{chain.upper.name}/{chain.lower.name}";

            SetCurve(clip, upperPath, "m_LocalRotation.x",
                new Keyframe(0f, 0f), WeightedKey(0.31f, 0f, 1.25f, 2.5f),
                new Keyframe(0.503f, 0.75f), WeightedKey(0.71f, 0f, -2.5f, -1.5f),
                new Keyframe(1f, 0f));
            SetCurve(clip, upperPath, "m_LocalRotation.y", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(clip, upperPath, "m_LocalRotation.z", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(clip, upperPath, "m_LocalRotation.w", new Keyframe(0f, 1f), new Keyframe(1f, 1f));
            AddIdentityRotationCurves(clip, lowerPath);
            AssetDatabase.SaveAssets();
            return (chain.root, chain.upper, chain.lower, chain.end, clip);
        }

        [Test]
        public void ContactMerge_PreservesOuterTangentsAndAddsExactBoundaries()
        {
            var fixture = CreateContactFixture("ContactMerge.anim");
            string upperPath = fixture.upper.name;
            var beforeCurve = GetCurve(fixture.clip, upperPath, "m_LocalRotation.x");
            Keyframe startBefore = KeyAt(beforeCurve, 0.31f);
            Keyframe endBefore = KeyAt(beforeCurve, 0.71f);
            float probeBefore = beforeCurve.Evaluate(0.2f);
            float probeAfter = beforeCurve.Evaluate(0.8f);
            float firstValueBefore = KeyAt(beforeCurve, 0f).value;
            float lastValueBefore = KeyAt(beforeCurve, 1f).value;

            var result = AnimationEffectorContactService.BakeContact(new EffectorContactBakeRequest
            {
                clipPath = AssetPath(fixture.clip),
                targetObjectPath = fixture.root.name,
                effector = "left_foot",
                targetType = "world_point",
                targetPosition = new[] { 1.5f, 0.4f, 0f },
                timeRange = new[] { 0.41f, 0.61f },
                blendInSeconds = 0.1f,
                blendOutSeconds = 0.1f,
                poleVector = new[] { 0f, 1f, 0f },
            });

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.backupId, Is.Not.Null.And.Not.Empty);
            var afterCurve = GetCurve(fixture.clip, upperPath, "m_LocalRotation.x");
            Assert.That(afterCurve.keys.Any(key => Mathf.Abs(key.time - 0.31f) < 0.0001f), Is.True);
            Assert.That(afterCurve.keys.Any(key => Mathf.Abs(key.time - 0.41f) < 0.0001f), Is.True);
            Assert.That(afterCurve.keys.Any(key => Mathf.Abs(key.time - 0.61f) < 0.0001f), Is.True);
            Assert.That(afterCurve.keys.Any(key => Mathf.Abs(key.time - 0.71f) < 0.0001f), Is.True);
            Assert.That(afterCurve.keys.Any(key => Mathf.Abs(key.time - 0.503f) < 0.0001f), Is.False);

            Keyframe startAfter = KeyAt(afterCurve, 0.31f);
            Keyframe endAfter = KeyAt(afterCurve, 0.71f);
            Assert.That(startAfter.inTangent, Is.EqualTo(startBefore.inTangent).Within(0.0001f));
            Assert.That(startAfter.inWeight, Is.EqualTo(startBefore.inWeight).Within(0.0001f));
            Assert.That(endAfter.outTangent, Is.EqualTo(endBefore.outTangent).Within(0.0001f));
            Assert.That(endAfter.outWeight, Is.EqualTo(endBefore.outWeight).Within(0.0001f));
            Assert.That(KeyAt(afterCurve, 0f).value, Is.EqualTo(firstValueBefore).Within(0.0001f));
            Assert.That(KeyAt(afterCurve, 1f).value, Is.EqualTo(lastValueBefore).Within(0.0001f));
            Assert.That(afterCurve.Evaluate(0.2f), Is.EqualTo(probeBefore).Within(0.0001f));
            Assert.That(afterCurve.Evaluate(0.8f), Is.EqualTo(probeAfter).Within(0.0001f));
            Assert.That(result.residualError, Is.LessThan(0.02f));
        }

        [Test]
        public void ContactMerge_RejectsMixedEulerAndQuaternionBindingsWithoutMutation()
        {
            var fixture = CreateContactFixture("MixedRotation.anim");
            SetCurve(fixture.clip, fixture.upper.name, "localEulerAnglesRaw.x", new Keyframe(0f, 0f), new Keyframe(1f, 10f));
            SetCurve(fixture.clip, fixture.upper.name, "localEulerAnglesRaw.y", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(fixture.clip, fixture.upper.name, "localEulerAnglesRaw.z", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            byte[] before = ReadAssetBytes(fixture.clip);

            var result = AnimationEffectorContactService.BakeContact(new EffectorContactBakeRequest
            {
                clipPath = AssetPath(fixture.clip),
                targetObjectPath = fixture.root.name,
                effector = "left_foot",
                targetType = "world_point",
                targetPosition = new[] { 1.5f, 0.4f, 0f },
                timeRange = new[] { 0.4f, 0.6f },
                blendInSeconds = 0.1f,
                blendOutSeconds = 0.1f,
            });

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("Euler"));
            Assert.That(ReadAssetBytes(fixture.clip), Is.EqualTo(before));
        }
    }
}
