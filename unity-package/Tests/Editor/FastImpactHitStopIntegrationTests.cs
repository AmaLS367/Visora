using NUnit.Framework;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class FastImpactHitStopIntegrationTests : AnimationIntegrationTestBase
    {
        [Test]
        public void SolveCameraSubjectContact_FastImpactAndHitStop_AuthorsSynchronizedCurvesAndRestoresScene()
        {
            var cameraGo = Track(new GameObject("ImpactCamera"));
            var camera = cameraGo.AddComponent<Camera>();
            cameraGo.transform.position = new Vector3(0f, 0.5f, -2f);
            cameraGo.transform.rotation = Quaternion.identity;

            var chain = CreateLegChain("ImpactCharacter", new Vector3(0f, 0.5f, 0f));
            Track(chain.root);

            var charClip = CreateClip("ImpactCharacter.anim");
            AddIdentityRotationCurves(charClip, chain.upper.name);
            AddIdentityRotationCurves(charClip, $"{chain.upper.name}/{chain.lower.name}");
            AddIdentityRotationCurves(charClip, $"{chain.upper.name}/{chain.lower.name}/{chain.end.name}");

            var camClip = CreateClip("ImpactCamera.anim");
            SetCurve(camClip, "", "m_LocalPosition.x", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(camClip, "", "m_LocalPosition.y", new Keyframe(0f, 0.5f), new Keyframe(1f, 0.5f));
            SetCurve(camClip, "", "m_LocalPosition.z", new Keyframe(0f, -2f), new Keyframe(1f, -2f));

            Vector3 cameraPosBefore = cameraGo.transform.position;
            Vector3 charPosBefore = chain.root.transform.position;

            var request = new CameraSubjectContactRequest
            {
                characterPath = chain.root.name,
                characterClipPath = AssetPath(charClip),
                cameraName = cameraGo.name,
                cameraClipPath = AssetPath(camClip),
                effector = "left_foot",
                impactTime = 0.4f,
                contactDuration = 0.2f,
                lensViewport = new[] { 0.5f, 0.5f },
                lensDistanceMeters = 1.8f,
                hitStopDuration = 0.08f,
                cameraRecoilImpulse = new[] { 0f, -0.1f, -0.3f },
            };

            var result = CameraSubjectActionService.SolveCameraSubjectContact(request);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.keyframesModifiedCount, Is.GreaterThan(0));
            Assert.That(result.impactWorldPosition, Is.Not.Null);

            // Assert camera recoil curves exist and have keys at impact
            var camCurveZ = GetCurve(camClip, "", "m_LocalPosition.z");
            Assert.That(camCurveZ, Is.Not.Null);
            Assert.That(camCurveZ.keys.Length, Is.GreaterThanOrEqualTo(4));
            var impactKey = System.Array.Find(camCurveZ.keys, k => Mathf.Abs(k.time - 0.4f) < 0.01f);
            Assert.That(impactKey.time, Is.EqualTo(0.4f).Within(0.01f));

            // Assert hit-stop holds on character clip
            string upperRel = chain.upper.name;
            var charUpperRotX = GetCurve(charClip, upperRel, "m_LocalRotation.x");
            Assert.That(charUpperRotX, Is.Not.Null);
            Assert.That(charUpperRotX.keys.Length, Is.GreaterThanOrEqualTo(2));

            // Verify scene state restoration: camera and character transforms remain at resting positions
            Assert.That(cameraGo.transform.position, Is.EqualTo(cameraPosBefore));
            Assert.That(chain.root.transform.position, Is.EqualTo(charPosBefore));
            Assert.That(GameObject.Find("Visora Preview Camera"), Is.Null);
        }
    }
}
