using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class HumanoidRigIntegrationTests : AnimationIntegrationTestBase
    {
        private GameObject CreateGenericRig(string name)
        {
            var root = Track(new GameObject(name));
            var pelvis = new GameObject("Pelvis").transform;
            var spine1 = new GameObject("Spine1").transform;
            var armA = new GameObject("Arm_A").transform;
            var armB = new GameObject("Arm_B").transform;
            var limbA = new GameObject("Limb_A").transform;

            pelvis.SetParent(root.transform, false);
            spine1.SetParent(pelvis, false);
            armA.SetParent(spine1, false);
            armB.SetParent(armA, false);
            limbA.SetParent(pelvis, false);

            root.AddComponent<Animator>();
            return root;
        }

        private (GameObject root, Dictionary<string, Transform> bones) CreateValidHumanoidRig(string name)
        {
            var root = Track(new GameObject(name));
            var bones = new Dictionary<string, Transform>();

            var hips = new GameObject("Hips").transform;
            hips.SetParent(root.transform, false);
            hips.localPosition = new Vector3(0f, 1f, 0f);
            bones["Hips"] = hips;

            var spine = new GameObject("Spine").transform;
            spine.SetParent(hips, false);
            spine.localPosition = new Vector3(0f, 0.3f, 0f);
            bones["Spine"] = spine;

            var head = new GameObject("Head").transform;
            head.SetParent(spine, false);
            head.localPosition = new Vector3(0f, 0.4f, 0f);
            bones["Head"] = head;

            // Left leg
            var lUpperLeg = new GameObject("LeftUpperLeg").transform;
            lUpperLeg.SetParent(hips, false);
            lUpperLeg.localPosition = new Vector3(-0.15f, -0.05f, 0f);
            bones["LeftUpperLeg"] = lUpperLeg;

            var lLowerLeg = new GameObject("LeftLowerLeg").transform;
            lLowerLeg.SetParent(lUpperLeg, false);
            lLowerLeg.localPosition = new Vector3(0f, -0.4f, 0f);
            bones["LeftLowerLeg"] = lLowerLeg;

            var lFoot = new GameObject("LeftFoot").transform;
            lFoot.SetParent(lLowerLeg, false);
            lFoot.localPosition = new Vector3(0f, -0.4f, 0.1f);
            bones["LeftFoot"] = lFoot;

            // Right leg
            var rUpperLeg = new GameObject("RightUpperLeg").transform;
            rUpperLeg.SetParent(hips, false);
            rUpperLeg.localPosition = new Vector3(0.15f, -0.05f, 0f);
            bones["RightUpperLeg"] = rUpperLeg;

            var rLowerLeg = new GameObject("RightLowerLeg").transform;
            rLowerLeg.SetParent(rUpperLeg, false);
            rLowerLeg.localPosition = new Vector3(0f, -0.4f, 0f);
            bones["RightLowerLeg"] = rLowerLeg;

            var rFoot = new GameObject("RightFoot").transform;
            rFoot.SetParent(rLowerLeg, false);
            rFoot.localPosition = new Vector3(0f, -0.4f, 0.1f);
            bones["RightFoot"] = rFoot;

            // Left arm (horizontal along -X in T-pose)
            var lUpperArm = new GameObject("LeftUpperArm").transform;
            lUpperArm.SetParent(spine, false);
            lUpperArm.localPosition = new Vector3(-0.2f, 0.2f, 0f);
            bones["LeftUpperArm"] = lUpperArm;

            var lLowerArm = new GameObject("LeftLowerArm").transform;
            lLowerArm.SetParent(lUpperArm, false);
            lLowerArm.localPosition = new Vector3(-0.35f, 0f, 0f);
            bones["LeftLowerArm"] = lLowerArm;

            var lHand = new GameObject("LeftHand").transform;
            lHand.SetParent(lLowerArm, false);
            lHand.localPosition = new Vector3(-0.25f, 0f, 0f);
            bones["LeftHand"] = lHand;

            // Right arm (horizontal along +X in T-pose)
            var rUpperArm = new GameObject("RightUpperArm").transform;
            rUpperArm.SetParent(spine, false);
            rUpperArm.localPosition = new Vector3(0.2f, 0.2f, 0f);
            bones["RightUpperArm"] = rUpperArm;

            var rLowerArm = new GameObject("RightLowerArm").transform;
            rLowerArm.SetParent(rUpperArm, false);
            rLowerArm.localPosition = new Vector3(0.35f, 0f, 0f);
            bones["RightLowerArm"] = rLowerArm;

            var rHand = new GameObject("RightHand").transform;
            rHand.SetParent(rLowerArm, false);
            rHand.localPosition = new Vector3(0.25f, 0f, 0f);
            bones["RightHand"] = rHand;

            root.AddComponent<Animator>();
            return (root, bones);
        }

        [Test]
        public void GenericRig_WithoutAvatar_IdentifiesMissingBonesAndBlockers()
        {
            var generic = CreateGenericRig("GenericRig_Test");

            var result = HumanoidService.ValidateAvatar(generic.name, null);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.isValidHumanoid, Is.False);
            Assert.That(result.avatarStatus, Is.EqualTo("missing_avatar"));
            Assert.That(result.missingRequiredBones, Contains.Item("Head"));
            Assert.That(result.missingRequiredBones, Contains.Item("LeftUpperLeg"));
            Assert.That(result.missingRequiredBones, Contains.Item("RightUpperLeg"));
            Assert.That(result.missingRequiredBones, Contains.Item("LeftUpperArm"));
            Assert.That(result.missingRequiredBones, Contains.Item("RightUpperArm"));

            var blocker = result.blockers.Find(b => b.boneName == "Head" && b.category == "missing_bone");
            Assert.That(blocker, Is.Not.Null);
            Assert.That(blocker.severity, Is.EqualTo("blocker"));
            Assert.That(blocker.suggestedFix, Does.Contain("Head"));
        }

        [Test]
        public void ValidHumanoidRig_WithAllRequiredBonesInTPose_ValidatesSuccessfully()
        {
            var (root, _) = CreateValidHumanoidRig("ValidHumanoid_Test");

            var result = HumanoidService.ValidateAvatar(root.name, null);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.missingRequiredBones, Is.Empty);
            Assert.That(result.blockers.FindAll(b => b.severity == "blocker"), Is.Empty);
            Assert.That(result.isValidHumanoid, Is.True);
            Assert.That(result.posture, Is.Not.Null);
            Assert.That(result.posture.isTpose, Is.True);
            Assert.That(result.posture.armsHorizontalAngle, Is.InRange(75f, 105f));
        }

        [Test]
        public void ValidHumanoidRig_ContactConstraintAnalysis_ResolvesAllLimbChains()
        {
            var (root, _) = CreateValidHumanoidRig("ValidHumanoidContact_Test");
            var clip = CreateClip("HumanoidContactTest.anim");
            SetCurve(clip, "Hips", "m_LocalPosition.y", new Keyframe(0f, 1f), new Keyframe(1f, 1f));

            var result = HumanoidContactService.AnalyzeContacts(
                root.name,
                AssetPath(clip),
                new[] { "left_foot", "right_foot", "left_hand", "right_hand" },
                "plane",
                0f,
                0.05f,
                0.02f);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.supportedEffectors.Count, Is.EqualTo(4));
            Assert.That(result.unsupportedEffectors, Is.Empty);

            var supportedNames = result.supportedEffectors.ConvertAll(e => e.effector);
            Assert.That(supportedNames, Contains.Item("left_foot"));
            Assert.That(supportedNames, Contains.Item("right_foot"));
            Assert.That(supportedNames, Contains.Item("left_hand"));
            Assert.That(supportedNames, Contains.Item("right_hand"));
        }
    }
}
