using System.Collections;
using NUnit.Framework;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class AnimationPreviewIntegrationTests : AnimationIntegrationTestBase
    {
        [Test]
        public void CapturePreviewRoutine_HighFpsAuthoredClip_GeneratesAccurateFramesAndRestoresPose()
        {
            var character = Track(new GameObject("PreviewCharacter"));
            var cameraGo = Track(new GameObject("PreviewCamera"));
            var camera = cameraGo.AddComponent<Camera>();
            cameraGo.transform.position = new Vector3(0f, 1f, -3f);
            cameraGo.transform.LookAt(character.transform);

            var clip = CreateClip("PreviewHighFps.anim", 24f);
            SetCurve(clip, "", "m_LocalPosition.x", new Keyframe(0f, 0f), new Keyframe(0.5f, 1f));
            SetCurve(clip, "", "m_LocalPosition.y", new Keyframe(0f, 0f), new Keyframe(0.5f, 0f));
            SetCurve(clip, "", "m_LocalPosition.z", new Keyframe(0f, 0f), new Keyframe(0.5f, 0f));

            Vector3 initialPosition = character.transform.localPosition;
            Quaternion initialRotation = character.transform.localRotation;

            var result = new AnimationPreviewSequenceResult();
            var routine = AnimationPreviewService.CapturePreviewRoutine(
                camera.name,
                AssetPath(clip),
                character.name,
                128,
                128,
                13,
                24f,
                0f,
                0.5f,
                false,
                result);

            while (routine.MoveNext()) { }

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.frameCount, Is.EqualTo(13));
            Assert.That(result.actualFps, Is.InRange(23.5f, 24.5f));
            Assert.That(result.frames.Count, Is.EqualTo(13));
            Assert.That(result.poseRestored, Is.True);
            Assert.That(character.transform.localPosition, Is.EqualTo(initialPosition));
            Assert.That(character.transform.localRotation, Is.EqualTo(initialRotation));
        }

        [Test]
        public void CapturePreviewRoutine_AutoFrameMisalignedCamera_CreatesAndDestroysPreviewCameraCleanly()
        {
            var character = Track(new GameObject("AutoFrameCharacter"));
            var rendererGo = GameObject.CreatePrimitive(PrimitiveType.Cube);
            rendererGo.transform.SetParent(character.transform, false);

            var cameraGo = Track(new GameObject("MisalignedCamera"));
            var camera = cameraGo.AddComponent<Camera>();
            cameraGo.transform.position = new Vector3(100f, 100f, 100f);

            var clip = CreateClip("AutoFramePreview.anim", 24f);
            SetCurve(clip, "", "m_LocalPosition.x", new Keyframe(0f, 0f), new Keyframe(0.2f, 0.5f));

            var result = new AnimationPreviewSequenceResult();
            var routine = AnimationPreviewService.CapturePreviewRoutine(
                camera.name,
                AssetPath(clip),
                character.name,
                64,
                64,
                5,
                24f,
                0f,
                0.2f,
                true,
                result);

            while (routine.MoveNext()) { }

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.previewCameraCreated, Is.True);
            Assert.That(result.previewCameraDestroyed, Is.True);
            Assert.That(GameObject.Find("Visora Preview Camera"), Is.Null);
            Assert.That(result.poseRestored, Is.True);
        }
    }
}
