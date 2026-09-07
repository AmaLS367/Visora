using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class NativeAvatarBlocker
    {
        public string boneName;
        public string category; // "missing_bone", "hierarchy", "posture", "duplicate_name", "scale"
        public string severity; // "blocker", "warning"
        public string message;
        public string suggestedFix;
    }

    [Serializable]
    public class NativeTPoseAssessment
    {
        public float armsHorizontalAngle;
        public float legsVerticalAngle;
        public bool isTpose;
        public bool isApose;
        public float symmetryScore;
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class NativeHumanoidValidationResult
    {
        public bool success = true;
        public string error;
        public string targetPath;
        public string assetPath;
        public bool isValidHumanoid;
        public string avatarStatus = "unknown";
        public List<NativeAvatarBlocker> blockers = new List<NativeAvatarBlocker>();
        public List<string> missingRequiredBones = new List<string>();
        public List<string> missingOptionalBones = new List<string>();
        public NativeTPoseAssessment posture;
        public Dictionary<string, string> boneMappings = new Dictionary<string, string>(StringComparer.Ordinal);
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class NativeHumanoidConfigurationResult
    {
        public bool success;
        public string error;
        public string assetPath;
        public string animationType = "Human";
        public bool avatarCreated;
        public bool avatarValid;
        public int configuredBonesCount;
        public List<NativeAvatarBlocker> blockers = new List<NativeAvatarBlocker>();
        public List<string> warnings = new List<string>();
    }

    public static class HumanoidService
    {
        private static readonly string[] RequiredHumanBones = new string[]
        {
            "Hips", "Spine", "Head",
            "LeftUpperLeg", "LeftLowerLeg", "LeftFoot",
            "RightUpperLeg", "RightLowerLeg", "RightFoot",
            "LeftUpperArm", "LeftLowerArm", "LeftHand",
            "RightUpperArm", "RightLowerArm", "RightHand"
        };

        private static readonly string[] OptionalHumanBones = new string[]
        {
            "Chest", "UpperChest", "Neck",
            "LeftShoulder", "RightShoulder",
            "LeftToes", "RightToes"
        };

        public static NativeHumanoidValidationResult ValidateAvatar(string targetPath, string assetPath)
        {
            var result = new NativeHumanoidValidationResult
            {
                targetPath = targetPath,
                assetPath = assetPath
            };

            GameObject rootGo = null;
            Avatar existingAvatar = null;
            bool isAsset = false;

            if (!string.IsNullOrEmpty(targetPath))
            {
                rootGo = GameObject.Find(targetPath);
                if (rootGo == null)
                {
                    result.success = false;
                    result.error = $"Target GameObject '{targetPath}' was not found in the active scene.";
                    return result;
                }
                var animator = rootGo.GetComponentInChildren<Animator>(true);
                if (animator != null && animator.avatar != null)
                {
                    existingAvatar = animator.avatar;
                }
            }
            else if (!string.IsNullOrEmpty(assetPath))
            {
                isAsset = true;
                var mainGo = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
                if (mainGo == null)
                {
                    result.success = false;
                    result.error = $"Asset at path '{assetPath}' could not be loaded as a GameObject.";
                    return result;
                }
                rootGo = mainGo;

                var subAssets = AssetDatabase.LoadAllAssetsAtPath(assetPath);
                foreach (var sub in subAssets)
                {
                    if (sub is Avatar av)
                    {
                        existingAvatar = av;
                        break;
                    }
                }
            }
            else
            {
                result.success = false;
                result.error = "Either targetPath or assetPath must be specified for humanoid validation.";
                return result;
            }

            // Check existing avatar status
            if (existingAvatar != null)
            {
                if (existingAvatar.isValid && existingAvatar.isHuman)
                {
                    result.avatarStatus = "valid_humanoid";
                    result.isValidHumanoid = true;
                }
                else if (existingAvatar.isValid)
                {
                    result.avatarStatus = "generic_avatar";
                }
                else
                {
                    result.avatarStatus = "invalid_avatar";
                }
            }
            else
            {
                result.avatarStatus = isAsset ? "not_configured" : "missing_avatar";
            }

            // Inspect Transforms
            var allTransforms = rootGo.GetComponentsInChildren<Transform>(true);
            var transformMap = new Dictionary<string, Transform>(StringComparer.OrdinalIgnoreCase);
            var nameCounts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

            foreach (var t in allTransforms)
            {
                if (nameCounts.TryGetValue(t.name, out int count))
                {
                    nameCounts[t.name] = count + 1;
                    if (count == 1)
                    {
                        result.blockers.Add(new NativeAvatarBlocker
                        {
                            boneName = t.name,
                            category = "duplicate_name",
                            severity = "blocker",
                            message = $"Duplicate bone name '{t.name}' detected in hierarchy.",
                            suggestedFix = "Rename bone transforms to have unique names across the skeleton."
                        });
                    }
                }
                else
                {
                    nameCounts[t.name] = 1;
                    transformMap[t.name] = t;
                }

                // Check negative scale
                var ls = t.localScale;
                if (ls.x < 0f || ls.y < 0f || ls.z < 0f)
                {
                    result.blockers.Add(new NativeAvatarBlocker
                    {
                        boneName = t.name,
                        category = "scale",
                        severity = "blocker",
                        message = $"Transform '{t.name}' has negative local scale ({ls.x:F3}, {ls.y:F3}, {ls.z:F3}).",
                        suggestedFix = "Freeze transform scales to positive 1.0 in modeling software or reset localScale."
                    });
                }
            }

            // Map bones from existing Avatar or heuristic
            if (existingAvatar != null && existingAvatar.isValid && existingAvatar.isHuman)
            {
                var desc = existingAvatar.humanDescription;
                foreach (var hb in desc.human)
                {
                    if (!string.IsNullOrEmpty(hb.humanName) && !string.IsNullOrEmpty(hb.boneName))
                    {
                        result.boneMappings[hb.humanName] = hb.boneName;
                    }
                }
            }
            else
            {
                // Heuristic matching for required and optional bones
                foreach (var req in RequiredHumanBones)
                {
                    var match = FindMatchingBone(req, transformMap);
                    if (match != null)
                    {
                        result.boneMappings[req] = match.name;
                    }
                }
                foreach (var opt in OptionalHumanBones)
                {
                    var match = FindMatchingBone(opt, transformMap);
                    if (match != null)
                    {
                        result.boneMappings[opt] = match.name;
                    }
                }
            }

            // Verify Required Bones
            foreach (var req in RequiredHumanBones)
            {
                if (!result.boneMappings.ContainsKey(req))
                {
                    result.missingRequiredBones.Add(req);
                    result.blockers.Add(new NativeAvatarBlocker
                    {
                        boneName = req,
                        category = "missing_bone",
                        severity = "blocker",
                        message = $"Required Humanoid bone '{req}' is not mapped or missing from skeleton.",
                        suggestedFix = $"Map a bone from the model to '{req}' in the Avatar definition."
                    });
                }
            }

            // Verify Optional Bones
            foreach (var opt in OptionalHumanBones)
            {
                if (!result.boneMappings.ContainsKey(opt))
                {
                    result.missingOptionalBones.Add(opt);
                    result.blockers.Add(new NativeAvatarBlocker
                    {
                        boneName = opt,
                        category = "missing_bone",
                        severity = "warning",
                        message = $"Optional bone '{opt}' is missing. Motion quality (e.g. torso flexion or foot roll) may be degraded.",
                        suggestedFix = $"If the rig contains a corresponding bone, map it to '{opt}'."
                    });
                }
            }

            // Hierarchy verification
            VerifyHierarchy(result, transformMap);

            // Posture assessment (T-pose vs A-pose)
            result.posture = EvaluatePosture(result.boneMappings, transformMap, result.blockers);

            // If any fatal blockers exist, isValidHumanoid is false
            bool hasFatalBlocker = false;
            foreach (var b in result.blockers)
            {
                if (string.Equals(b.severity, "blocker", StringComparison.OrdinalIgnoreCase))
                {
                    hasFatalBlocker = true;
                    break;
                }
            }
            result.isValidHumanoid = !hasFatalBlocker && result.missingRequiredBones.Count == 0;

            return result;
        }

        private static void VerifyHierarchy(NativeHumanoidValidationResult result, Dictionary<string, Transform> map)
        {
            // Head must be descendant of Spine
            if (result.boneMappings.TryGetValue("Head", out var headName) &&
                result.boneMappings.TryGetValue("Spine", out var spineName))
            {
                if (map.TryGetValue(headName, out var headT) && map.TryGetValue(spineName, out var spineT))
                {
                    if (!headT.IsChildOf(spineT))
                    {
                        result.blockers.Add(new NativeAvatarBlocker
                        {
                            boneName = headName,
                            category = "hierarchy",
                            severity = "blocker",
                            message = $"Bone mapped to Head ('{headName}') is not a descendant of Spine ('{spineName}').",
                            suggestedFix = "Ensure the skeletal hierarchy connects Head under Spine/Neck."
                        });
                    }
                }
            }

            // LeftHand must be descendant of LeftUpperArm
            if (result.boneMappings.TryGetValue("LeftHand", out var lHandName) &&
                result.boneMappings.TryGetValue("LeftUpperArm", out var lArmName))
            {
                if (map.TryGetValue(lHandName, out var lHandT) && map.TryGetValue(lArmName, out var lArmT))
                {
                    if (!lHandT.IsChildOf(lArmT))
                    {
                        result.blockers.Add(new NativeAvatarBlocker
                        {
                            boneName = lHandName,
                            category = "hierarchy",
                            severity = "blocker",
                            message = $"LeftHand ('{lHandName}') is not a descendant of LeftUpperArm ('{lArmName}').",
                            suggestedFix = "Fix limb hierarchy so Hand descends from Forearm/UpperArm."
                        });
                    }
                }
            }

            // RightHand must be descendant of RightUpperArm
            if (result.boneMappings.TryGetValue("RightHand", out var rHandName) &&
                result.boneMappings.TryGetValue("RightUpperArm", out var rArmName))
            {
                if (map.TryGetValue(rHandName, out var rHandT) && map.TryGetValue(rArmName, out var rArmT))
                {
                    if (!rHandT.IsChildOf(rArmT))
                    {
                        result.blockers.Add(new NativeAvatarBlocker
                        {
                            boneName = rHandName,
                            category = "hierarchy",
                            severity = "blocker",
                            message = $"RightHand ('{rHandName}') is not a descendant of RightUpperArm ('{rArmName}').",
                            suggestedFix = "Fix limb hierarchy so Hand descends from Forearm/UpperArm."
                        });
                    }
                }
            }

            // LeftFoot must be descendant of LeftUpperLeg
            if (result.boneMappings.TryGetValue("LeftFoot", out var lFootName) &&
                result.boneMappings.TryGetValue("LeftUpperLeg", out var lLegName))
            {
                if (map.TryGetValue(lFootName, out var lFootT) && map.TryGetValue(lLegName, out var lLegT))
                {
                    if (!lFootT.IsChildOf(lLegT))
                    {
                        result.blockers.Add(new NativeAvatarBlocker
                        {
                            boneName = lFootName,
                            category = "hierarchy",
                            severity = "blocker",
                            message = $"LeftFoot ('{lFootName}') is not a descendant of LeftUpperLeg ('{lLegName}').",
                            suggestedFix = "Ensure Leg chain is Hips -> UpperLeg -> LowerLeg -> Foot."
                        });
                    }
                }
            }

            // RightFoot must be descendant of RightUpperLeg
            if (result.boneMappings.TryGetValue("RightFoot", out var rFootName) &&
                result.boneMappings.TryGetValue("RightUpperLeg", out var rLegName))
            {
                if (map.TryGetValue(rFootName, out var rFootT) && map.TryGetValue(rLegName, out var rLegT))
                {
                    if (!rFootT.IsChildOf(rLegT))
                    {
                        result.blockers.Add(new NativeAvatarBlocker
                        {
                            boneName = rFootName,
                            category = "hierarchy",
                            severity = "blocker",
                            message = $"RightFoot ('{rFootName}') is not a descendant of RightUpperLeg ('{rLegName}').",
                            suggestedFix = "Ensure Leg chain is Hips -> UpperLeg -> LowerLeg -> Foot."
                        });
                    }
                }
            }
        }

        private static NativeTPoseAssessment EvaluatePosture(
            Dictionary<string, string> mappings,
            Dictionary<string, Transform> map,
            List<NativeAvatarBlocker> blockers)
        {
            var assessment = new NativeTPoseAssessment
            {
                armsHorizontalAngle = 90f,
                legsVerticalAngle = 0f,
                isTpose = true,
                isApose = false,
                symmetryScore = 1f
            };

            // Measure arm angle relative to horizontal / spine
            Transform lArmT = null, rArmT = null, lForearmT = null, rForearmT = null;
            if (mappings.TryGetValue("LeftUpperArm", out var lArmName)) map.TryGetValue(lArmName, out lArmT);
            if (mappings.TryGetValue("RightUpperArm", out var rArmName)) map.TryGetValue(rArmName, out rArmT);
            if (mappings.TryGetValue("LeftLowerArm", out var lForearmName)) map.TryGetValue(lForearmName, out lForearmT);
            if (mappings.TryGetValue("RightLowerArm", out var rForearmName)) map.TryGetValue(rForearmName, out rForearmT);

            if (lArmT != null && lForearmT != null && rArmT != null && rForearmT != null)
            {
                var lArmDir = (lForearmT.position - lArmT.position).normalized;
                var rArmDir = (rForearmT.position - rArmT.position).normalized;

                // Angle with Vector3.down (180 = straight up, 90 = horizontal, 0 = straight down)
                float lAngleDown = Vector3.Angle(lArmDir, Vector3.down);
                float rAngleDown = Vector3.Angle(rArmDir, Vector3.down);
                float avgAngleDown = (lAngleDown + rAngleDown) * 0.5f;
                assessment.armsHorizontalAngle = avgAngleDown;

                // In T-pose: avgAngleDown is approx 80° - 100° (horizontal).
                // In A-pose: avgAngleDown is approx 40° - 55° (pointing down).
                if (avgAngleDown < 65f)
                {
                    assessment.isApose = true;
                    assessment.isTpose = false;
                    blockers.Add(new NativeAvatarBlocker
                    {
                        boneName = "Arms",
                        category = "posture",
                        severity = "warning",
                        message = $"Arms appear to be in an A-pose (average angle {avgAngleDown:F1}° to vertical, ~{90f - avgAngleDown:F1}° below horizontal).",
                        suggestedFix = "Unity Humanoid retargeting is calibrated for T-pose (arms horizontal at ~90°). Consider normalizing bind pose to T-pose."
                    });
                }
                else if (avgAngleDown >= 75f && avgAngleDown <= 105f)
                {
                    assessment.isTpose = true;
                    assessment.isApose = false;
                }

                // Symmetry score
                float angleDiff = Mathf.Abs(lAngleDown - rAngleDown);
                assessment.symmetryScore = Mathf.Clamp01(1f - (angleDiff / 90f));
            }

            return assessment;
        }

        private static Transform FindMatchingBone(string humanBoneName, Dictionary<string, Transform> map)
        {
            // Exact match
            if (map.TryGetValue(humanBoneName, out var exact)) return exact;

            // Common naming patterns
            var patterns = GetBoneSearchPatterns(humanBoneName);
            foreach (var p in patterns)
            {
                foreach (var kvp in map)
                {
                    if (kvp.Key.Contains(p, StringComparison.OrdinalIgnoreCase))
                    {
                        return kvp.Value;
                    }
                }
            }
            return null;
        }

        private static readonly Dictionary<string, string[]> BoneSearchPatterns = new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            ["Hips"] = new[] { "hip", "pelvis", "root" },
            ["Spine"] = new[] { "spine_01", "spine1", "spine" },
            ["Chest"] = new[] { "chest", "spine_02", "spine2" },
            ["UpperChest"] = new[] { "upperchest", "spine_03", "spine3" },
            ["Neck"] = new[] { "neck" },
            ["Head"] = new[] { "head" },
            ["LeftUpperLeg"] = new[] { "thigh_l", "upperleg_l", "leg_l", "leftupleg", "leftleg" },
            ["LeftLowerLeg"] = new[] { "calf_l", "lowerleg_l", "knee_l", "shin_l", "leftleg" },
            ["LeftFoot"] = new[] { "foot_l", "ankle_l", "leftfoot" },
            ["LeftToes"] = new[] { "toe_l", "ball_l", "lefttoebase" },
            ["RightUpperLeg"] = new[] { "thigh_r", "upperleg_r", "leg_r", "rightupleg", "rightleg" },
            ["RightLowerLeg"] = new[] { "calf_r", "lowerleg_r", "knee_r", "shin_r", "rightleg" },
            ["RightFoot"] = new[] { "foot_r", "ankle_r", "rightfoot" },
            ["RightToes"] = new[] { "toe_r", "ball_r", "righttoebase" },
            ["LeftShoulder"] = new[] { "clavicle_l", "shoulder_l", "leftshoulder" },
            ["LeftUpperArm"] = new[] { "upperarm_l", "arm_l", "leftarm", "leftshoulder" },
            ["LeftLowerArm"] = new[] { "forearm_l", "lowerarm_l", "elbow_l", "leftforearm" },
            ["LeftHand"] = new[] { "hand_l", "wrist_l", "lefthand" },
            ["RightShoulder"] = new[] { "clavicle_r", "shoulder_r", "rightshoulder" },
            ["RightUpperArm"] = new[] { "upperarm_r", "arm_r", "rightarm", "rightshoulder" },
            ["RightLowerArm"] = new[] { "forearm_r", "lowerarm_r", "elbow_r", "rightforearm" },
            ["RightHand"] = new[] { "hand_r", "wrist_r", "righthand" },
        };

        private static string[] GetBoneSearchPatterns(string humanBoneName)
        {
            if (BoneSearchPatterns.TryGetValue(humanBoneName, out var patterns))
            {
                return patterns;
            }
            return new[] { humanBoneName };
        }

        public static NativeHumanoidConfigurationResult ConfigureHumanoid(
            string assetPath,
            Dictionary<string, string> boneOverrides,
            string sourceAvatarPath)
        {
            var result = new NativeHumanoidConfigurationResult
            {
                assetPath = assetPath
            };

            if (string.IsNullOrEmpty(assetPath))
            {
                result.success = false;
                result.error = "assetPath must be specified.";
                return result;
            }

            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            if (importer == null)
            {
                result.success = false;
                result.error = $"Asset at path '{assetPath}' is not a 3D model (ModelImporter not found).";
                return result;
            }

            importer.animationType = ModelImporterAnimationType.Human;

            if (!string.IsNullOrEmpty(sourceAvatarPath))
            {
                var sourceAvatar = AssetDatabase.LoadAssetAtPath<Avatar>(sourceAvatarPath);
                if (sourceAvatar == null)
                {
                    result.success = false;
                    result.error = $"Source avatar could not be loaded at path: '{sourceAvatarPath}'";
                    return result;
                }
                importer.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                importer.sourceAvatar = sourceAvatar;
            }
            else
            {
                importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;

                if (boneOverrides != null && boneOverrides.Count > 0)
                {
                    var humanBones = new List<HumanBone>();
                    foreach (var kvp in boneOverrides)
                    {
                        var hb = new HumanBone
                        {
                            humanName = kvp.Key,
                            boneName = kvp.Value
                        };
                        hb.limit.useDefaultValues = true;
                        humanBones.Add(hb);
                    }

                    var desc = importer.humanDescription;
                    desc.human = humanBones.ToArray();
                    importer.humanDescription = desc;
                    result.configuredBonesCount = humanBones.Count;
                }
            }

            try
            {
                AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Asset reimport failed: {ex.Message}";
                return result;
            }

            // Verify generated avatar
            var subAssets = AssetDatabase.LoadAllAssetsAtPath(assetPath);
            Avatar newAvatar = null;
            foreach (var sub in subAssets)
            {
                if (sub is Avatar av)
                {
                    newAvatar = av;
                    break;
                }
            }

            if (newAvatar != null)
            {
                result.avatarCreated = true;
                result.avatarValid = newAvatar.isValid && newAvatar.isHuman;
                if (!result.avatarValid)
                {
                    result.warnings.Add("Avatar was created but is reported as invalid or non-human by Unity.");
                }
            }
            else
            {
                result.avatarCreated = false;
                result.avatarValid = false;
                result.warnings.Add("Model reimported as Human, but no Avatar sub-asset was generated.");
            }

            result.success = true;
            return result;
        }
    }
}
