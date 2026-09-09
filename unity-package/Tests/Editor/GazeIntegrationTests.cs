using NUnit.Framework;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class GazeIntegrationTests : AnimationIntegrationTestBase
    {
        private (GameObject root, Transform chest, Transform neck, Transform head, Transform leftEye, Transform rightEye)
            CreateGazeRig(string name, Vector3 position)
        {
            var root = Track(new GameObject(name));
            root.transform.position = position;
            var chest = new GameObject("Chest").transform;
            var neck = new GameObject("Neck").transform;
            var head = new GameObject("Head").transform;
            var leftEye = new GameObject("LeftEye").transform;
            var rightEye = new GameObject("RightEye").transform;
            chest.SetParent(root.transform, false);
            neck.SetParent(chest, false);
            head.SetParent(neck, false);
            leftEye.SetParent(head, false);
            rightEye.SetParent(head, false);
            chest.localPosition = new Vector3(0f, 1f, 0f);
            neck.localPosition = new Vector3(0f, 0.5f, 0f);
            head.localPosition = new Vector3(0f, 0.3f, 0f);
            leftEye.localPosition = new Vector3(-0.03f, 0.05f, 0.08f);
            rightEye.localPosition = new Vector3(0.03f, 0.05f, 0.08f);
            return (root, chest, neck, head, leftEye, rightEye);
        }

        [Test]
        public void EyeOnlyGaze_UsesActualEyesForResidualAndRestoresQueryPose()
        {
            var rig = CreateGazeRig("GazeEyes", Vector3.zero);
            Quaternion leftBefore = rig.leftEye.localRotation;
            Quaternion rightBefore = rig.rightEye.localRotation;
            var target = new Vector3(2f, rig.head.position.y, 10f);

            var applied = GazeService.SolveCharacterGaze(
                rig.root.name, new[] { target.x, target.y, target.z }, null,
                0f, 0f, 0f, 1f, new[] { 0f, 1f, 0f }, true, null, null);

            float leftResidual = Vector3.Angle(rig.leftEye.forward, (target - rig.leftEye.position).normalized);
            float rightResidual = Vector3.Angle(rig.rightEye.forward, (target - rig.rightEye.position).normalized);
            Assert.That(applied.success, Is.True, applied.error);
            Assert.That(leftResidual, Is.LessThan(2f));
            Assert.That(rightResidual, Is.LessThan(2f));
            Assert.That(applied.residualGazeErrorDeg, Is.LessThan(2f));

            rig.leftEye.localRotation = leftBefore;
            rig.rightEye.localRotation = rightBefore;
            var queried = GazeService.SolveCharacterGaze(
                rig.root.name, new[] { target.x, target.y, target.z }, null,
                0f, 0f, 0f, 1f, new[] { 0f, 1f, 0f }, false, null, null);
            Assert.That(queried.success, Is.True, queried.error);
            Assert.That(Quaternion.Angle(rig.leftEye.localRotation, leftBefore), Is.LessThan(0.001f));
            Assert.That(Quaternion.Angle(rig.rightEye.localRotation, rightBefore), Is.LessThan(0.001f));
        }

        [Test]
        public void CustomUpVector_ChangesTheSolvedOrientation()
        {
            var worldUpRig = CreateGazeRig("GazeWorldUp", Vector3.zero);
            var customUpRig = CreateGazeRig("GazeCustomUp", new Vector3(5f, 0f, 0f));
            Vector3 offset = new Vector3(2f, 2f, 8f);
            Vector3 targetA = worldUpRig.head.position + offset;
            Vector3 targetB = customUpRig.head.position + offset;

            var worldUpResult = GazeService.SolveCharacterGaze(
                worldUpRig.root.name, new[] { targetA.x, targetA.y, targetA.z }, null,
                0f, 0f, 1f, 0f, new[] { 0f, 1f, 0f }, true, null, null);
            var customUpResult = GazeService.SolveCharacterGaze(
                customUpRig.root.name, new[] { targetB.x, targetB.y, targetB.z }, null,
                0f, 0f, 1f, 0f, new[] { 1f, 0f, 0f }, true, null, null);

            Assert.That(worldUpResult.success, Is.True, worldUpResult.error);
            Assert.That(customUpResult.success, Is.True, customUpResult.error);
            Assert.That(Quaternion.Angle(worldUpRig.head.rotation, customUpRig.head.rotation), Is.GreaterThan(1f));
        }

        [Test]
        public void MissingChestAndNeck_TransfersTheirWeightsToHead()
        {
            var root = Track(new GameObject("GazeHeadOnly"));
            var head = new GameObject("Head").transform;
            head.SetParent(root.transform, false);
            Vector3 target = new Vector3(10f, 0f, 10f);

            var result = GazeService.SolveCharacterGaze(
                root.name, new[] { target.x, target.y, target.z }, null,
                0.5f, 0f, 0.5f, 0f, new[] { 0f, 1f, 0f }, true, null, null);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.residualGazeErrorDeg, Is.LessThan(2f));
        }

        [Test]
        public void ZeroUpVector_IsRejected()
        {
            var rig = CreateGazeRig("GazeZeroUp", Vector3.zero);
            var result = GazeService.SolveCharacterGaze(
                rig.root.name, new[] { 0f, 2f, 10f }, null,
                0.15f, 0.35f, 0.4f, 0.1f, new[] { 0f, 0f, 0f }, false, null, null);
            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("upVector"));
        }

        [Test]
        public void VerticalTargetWithoutChestOrNeck_RemainsFiniteAndUsesHead()
        {
            var root = Track(new GameObject("GazeVerticalHeadOnly"));
            var head = new GameObject("Head").transform;
            head.SetParent(root.transform, false);
            Vector3 target = head.position + (Vector3.up * 10f);

            var result = GazeService.SolveCharacterGaze(
                root.name, new[] { target.x, target.y, target.z }, null,
                0.3f, 0.3f, 0.4f, 0f, new[] { 0f, 1f, 0f }, true, null, null);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.solvedJoints, Has.Count.EqualTo(1));
            Assert.That(float.IsNaN(result.residualGazeErrorDeg), Is.False);
            Assert.That(float.IsInfinity(result.residualGazeErrorDeg), Is.False);
            Assert.That(result.wasClamped, Is.True);
        }
    }
}
