using System.Collections.Generic;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class AnimationAtomicityIntegrationTests : AnimationIntegrationTestBase
    {
        [Test]
        public void AnimationTransaction_FailureRestoresCurveAndAssetBytes()
        {
            var clip = CreateClip("Transaction.anim");
            SetCurve(clip, "", "m_LocalPosition.x", new Keyframe(0f, 0f), new Keyframe(1f, 1f));
            SetCurve(clip, "", "m_LocalPosition.y", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(clip, "", "m_LocalPosition.z", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            byte[] before = ReadAssetBytes(clip);

            var request = new AnimationTransactionRequest
            {
                description = "Visora rollback integration test",
                operations = new List<AnimationTransactionOperation>
                {
                    new AnimationTransactionOperation
                    {
                        operationType = "set_keyframe",
                        clipPath = AssetPath(clip),
                        targetPath = "",
                        typeName = "Transform",
                        propertyName = "m_LocalPosition",
                        time = 0.5f,
                        values = new[] { 5f, 0f, 0f },
                    },
                    new AnimationTransactionOperation
                    {
                        operationType = "unsupported_operation",
                        clipPath = AssetPath(clip),
                    },
                },
            };

            var result = AnimationTransactionService.ExecuteTransaction(request);
            var restored = AssetDatabase.LoadAssetAtPath<AnimationClip>(AssetPath(clip));
            byte[] after = ReadAssetBytes(restored);

            Assert.That(result.success, Is.False);
            Assert.That(result.rollbackPerformed, Is.True);
            Assert.That(after, Is.EqualTo(before));
            Assert.That(GetCurve(restored, "", "m_LocalPosition.x").keys, Has.Length.EqualTo(2));
        }

        [Test]
        public void CameraSubject_InvalidCameraClipFailsBeforeCharacterMutation()
        {
            var cameraGo = Track(new GameObject("AtomicCamera"));
            cameraGo.AddComponent<Camera>();
            cameraGo.transform.position = new Vector3(0f, 0f, -2f);
            var chain = CreateLegChain("AtomicCharacter", new Vector3(-1f, 0f, 0f));
            Track(chain.root);
            var characterClip = CreateClip("Character.anim");
            AddIdentityRotationCurves(characterClip, chain.upper.name);
            AddIdentityRotationCurves(characterClip, $"{chain.upper.name}/{chain.lower.name}");
            byte[] before = ReadAssetBytes(characterClip);

            var result = CameraSubjectActionService.SolveCameraSubjectContact(new CameraSubjectContactRequest
            {
                characterPath = chain.root.name,
                characterClipPath = AssetPath(characterClip),
                cameraName = cameraGo.name,
                cameraClipPath = $"{TestAssetFolder}/Missing.anim",
                effector = "left_foot",
                impactTime = 0.4f,
                contactDuration = 0.2f,
                lensViewport = new[] { 0.5f, 0.5f },
                lensDistanceMeters = 2f,
                hitStopDuration = 0.08f,
            });

            var restored = AssetDatabase.LoadAssetAtPath<AnimationClip>(AssetPath(characterClip));
            Assert.That(result.success, Is.False);
            Assert.That(ReadAssetBytes(restored), Is.EqualTo(before));
        }

        [Test]
        public void CameraSubject_FailureAfterCameraMutationRestoresBothAssetFiles()
        {
            var cameraGo = Track(new GameObject("RollbackCamera"));
            cameraGo.AddComponent<Camera>();
            cameraGo.transform.position = new Vector3(0f, 0f, -5f);
            var chain = CreateLegChain("RollbackCharacter", new Vector3(-1f, 0f, 0f));
            Track(chain.root);

            var characterClip = CreateClip("RollbackCharacter.anim");
            AddIdentityRotationCurves(characterClip, chain.upper.name);
            AddIdentityRotationCurves(characterClip, $"{chain.upper.name}/{chain.lower.name}");
            // The camera keys are authored before contact validation reaches this conflict.
            SetCurve(characterClip, chain.upper.name, "localEulerAnglesRaw.x",
                new Keyframe(0f, 0f), new Keyframe(1f, 5f));

            var cameraClip = CreateClip("RollbackCamera.anim");
            SetCurve(cameraClip, "", "m_LocalPosition.x", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(cameraClip, "", "m_LocalPosition.y", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(cameraClip, "", "m_LocalPosition.z", new Keyframe(0f, -5f), new Keyframe(1f, -5f));

            byte[] characterBefore = ReadAssetBytes(characterClip);
            byte[] cameraBefore = ReadAssetBytes(cameraClip);

            var result = CameraSubjectActionService.SolveCameraSubjectContact(new CameraSubjectContactRequest
            {
                characterPath = chain.root.name,
                characterClipPath = AssetPath(characterClip),
                cameraName = cameraGo.name,
                cameraClipPath = AssetPath(cameraClip),
                effector = "left_foot",
                impactTime = 0.4f,
                contactDuration = 0.2f,
                lensViewport = new[] { 0.7f, 0.6f },
                lensDistanceMeters = 5f,
                hitStopDuration = 0.08f,
            });

            var restoredCharacter = AssetDatabase.LoadAssetAtPath<AnimationClip>(AssetPath(characterClip));
            var restoredCamera = AssetDatabase.LoadAssetAtPath<AnimationClip>(AssetPath(cameraClip));
            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("Euler"));
            Assert.That(ReadAssetBytes(restoredCharacter), Is.EqualTo(characterBefore));
            Assert.That(ReadAssetBytes(restoredCamera), Is.EqualTo(cameraBefore));
        }

        [Test]
        public void CameraSubject_ResidualUsesSampledEffectorInsteadOfRequestedViewportPoint()
        {
            var cameraGo = Track(new GameObject("MetricCamera"));
            var camera = cameraGo.AddComponent<Camera>();
            cameraGo.transform.position = new Vector3(0f, 0f, -5f);
            var chain = CreateLegChain("MetricCharacter", new Vector3(-1f, 0f, 0f));
            Track(chain.root);

            var characterClip = CreateClip("MetricCharacter.anim");
            AddIdentityRotationCurves(characterClip, chain.upper.name);
            AddIdentityRotationCurves(characterClip, $"{chain.upper.name}/{chain.lower.name}");
            var cameraClip = CreateClip("MetricCamera.anim");
            SetCurve(cameraClip, "", "m_LocalPosition.x", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(cameraClip, "", "m_LocalPosition.y", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(cameraClip, "", "m_LocalPosition.z", new Keyframe(0f, -5f), new Keyframe(1f, -5f));

            const float impactTime = 0.4f;
            var result = CameraSubjectActionService.SolveCameraSubjectContact(new CameraSubjectContactRequest
            {
                characterPath = chain.root.name,
                characterClipPath = AssetPath(characterClip),
                cameraName = cameraGo.name,
                cameraClipPath = AssetPath(cameraClip),
                effector = "left_foot",
                impactTime = impactTime,
                contactDuration = 0.2f,
                lensViewport = new[] { 0.8f, 0.7f },
                lensDistanceMeters = 5f,
                cameraRecoilImpulse = new[] { 0f, 0f, 0f },
            });

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.impactScreenResidualPixels[0] + result.impactScreenResidualPixels[1], Is.GreaterThan(1f));

            Vector3 sampledEffector = Vector3.zero;
            AnimationMode.StartAnimationMode();
            try
            {
                AnimationMode.BeginSampling();
                AnimationMode.SampleAnimationClip(chain.root, characterClip, impactTime);
                AnimationMode.SampleAnimationClip(cameraGo, cameraClip, impactTime);
                AnimationMode.EndSampling();
                sampledEffector = chain.end.position;
                Vector3 viewport = camera.WorldToViewportPoint(sampledEffector);
                Assert.That(result.impactScreenResidualPixels[0],
                    Is.EqualTo(Mathf.Abs(viewport.x - 0.8f) * camera.pixelWidth).Within(0.01f));
                Assert.That(result.impactScreenResidualPixels[1],
                    Is.EqualTo(Mathf.Abs(viewport.y - 0.7f) * camera.pixelHeight).Within(0.01f));
            }
            finally
            {
                if (AnimationMode.InAnimationMode()) AnimationMode.StopAnimationMode();
            }

            Assert.That(result.impactWorldPosition[0], Is.EqualTo(sampledEffector.x).Within(0.0001f));
            Assert.That(result.impactWorldPosition[1], Is.EqualTo(sampledEffector.y).Within(0.0001f));
            Assert.That(result.impactWorldPosition[2], Is.EqualTo(sampledEffector.z).Within(0.0001f));
        }
    }
}
