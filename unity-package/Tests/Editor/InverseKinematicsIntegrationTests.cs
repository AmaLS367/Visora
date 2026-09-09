using NUnit.Framework;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class InverseKinematicsIntegrationTests : AnimationIntegrationTestBase
    {
        [Test]
        public void ReachableTarget_PreservesLengthsAndPlacesEffector()
        {
            var chain = CreateLegChain("IKReachable", Vector3.zero);
            Track(chain.root);
            float firstLength = Vector3.Distance(chain.upper.position, chain.lower.position);
            float secondLength = Vector3.Distance(chain.lower.position, chain.end.position);

            InverseKinematicsService.SolveTwoBoneIKInternal(
                chain.upper, chain.lower, chain.end, new Vector3(1.5f, 0f, 0f), null, new Vector3(0f, 1f, 0f), 1f,
                out bool clamped, out _, out _, out float residual, out _);

            Assert.That(clamped, Is.False);
            Assert.That(residual, Is.LessThan(0.001f));
            Assert.That(Vector3.Distance(chain.upper.position, chain.lower.position), Is.EqualTo(firstLength).Within(0.0001f));
            Assert.That(Vector3.Distance(chain.lower.position, chain.end.position), Is.EqualTo(secondLength).Within(0.0001f));
        }

        [Test]
        public void PoleVector_SelectsRequestedHalfPlane()
        {
            var positive = CreateLegChain("IKPolePositive", Vector3.zero);
            var negative = CreateLegChain("IKPoleNegative", new Vector3(0f, 0f, 3f));
            Track(positive.root);
            Track(negative.root);

            InverseKinematicsService.SolveTwoBoneIKInternal(
                positive.upper, positive.lower, positive.end, new Vector3(1.5f, 0f, 0f), null,
                new Vector3(0f, 1f, 0f), 1f, out _, out _, out _, out _, out _);
            InverseKinematicsService.SolveTwoBoneIKInternal(
                negative.upper, negative.lower, negative.end, new Vector3(1.5f, 0f, 3f), null,
                new Vector3(0f, -1f, 3f), 1f, out _, out _, out _, out _, out _);

            Assert.That(positive.lower.position.y, Is.GreaterThan(0.01f), "A +Y pole must bend toward +Y.");
            Assert.That(negative.lower.position.y, Is.LessThan(-0.01f), "A -Y pole must bend toward -Y.");
        }

        [Test]
        public void UnreachableAndDegenerateTargets_AreClampedWithoutNaN()
        {
            var chain = CreateLegChain("IKClamped", Vector3.zero);
            Track(chain.root);
            InverseKinematicsService.SolveTwoBoneIKInternal(
                chain.upper, chain.lower, chain.end, new Vector3(10f, 0f, 0f), null, Vector3.up, 1f,
                out bool clamped, out float reach, out _, out float residual, out _);

            Assert.That(clamped, Is.True);
            Assert.That(Vector3.Distance(chain.upper.position, chain.end.position), Is.LessThanOrEqualTo(reach + 0.001f));
            Assert.That(float.IsNaN(residual), Is.False);

            chain.end.localPosition = Vector3.zero;
            Assert.DoesNotThrow(() => InverseKinematicsService.SolveTwoBoneIKInternal(
                chain.upper, chain.lower, chain.end, chain.upper.position, null, Vector3.up, 1f,
                out _, out _, out _, out _, out _));
            Assert.That(float.IsNaN(chain.upper.rotation.x), Is.False);
            Assert.That(float.IsNaN(chain.lower.rotation.x), Is.False);
        }

        [Test]
        public void ViewportQuery_MeasuresSolvedPoseAndRestoresScenePose()
        {
            var cameraGo = Track(new GameObject("VisoraViewportCamera"));
            var camera = cameraGo.AddComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = 2f;
            camera.aspect = 1f;
            camera.pixelRect = new Rect(0f, 0f, 1000f, 1000f);
            cameraGo.transform.position = new Vector3(0f, 0f, -5f);

            var chain = CreateLegChain("ViewportCharacter", new Vector3(-1f, 0f, 0f));
            Track(chain.root);
            Quaternion rootBefore = chain.upper.localRotation;
            Quaternion midBefore = chain.lower.localRotation;
            Quaternion endBefore = chain.end.localRotation;

            var result = InverseKinematicsService.PlaceEffectorInViewport(
                cameraGo.name, chain.root.name, null, chain.upper.name, chain.lower.name, chain.end.name,
                0.5f, 0.5f, 5f, "match_camera_rotation", null, new[] { 0f, 1f, 0f }, 1f, false, null, null);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.actualViewport[0], Is.EqualTo(0.5f).Within(0.001f));
            Assert.That(result.actualViewport[1], Is.EqualTo(0.5f).Within(0.001f));
            Assert.That(result.actualViewport[2], Is.EqualTo(5f).Within(0.001f));
            Assert.That(Quaternion.Angle(chain.upper.localRotation, rootBefore), Is.LessThan(0.001f));
            Assert.That(Quaternion.Angle(chain.lower.localRotation, midBefore), Is.LessThan(0.001f));
            Assert.That(Quaternion.Angle(chain.end.localRotation, endBefore), Is.LessThan(0.001f));
        }
    }
}
