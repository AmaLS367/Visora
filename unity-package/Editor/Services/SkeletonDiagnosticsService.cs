using System;
using System.Collections.Generic;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class BoneNode
    {
        public string name;
        public string path;
        public float[] localPosition;
        public float[] localRotation;
        public float[] localScale;
        public int childCount;
        public List<BoneNode> children = new List<BoneNode>();
    }

    [Serializable]
    public class SkeletonDiagnosticsResult
    {
        public bool success;
        public string error;
        public string rootName;
        public int totalBones;
        public List<string> duplicateBones = new List<string>();
        public List<string> mmdChains = new List<string>();
        public List<string> matchingBones = new List<string>();
        public BoneNode hierarchy;
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Introspects skeletons, hierarchies, bone names, and MMD D-bone rigs.
    /// </summary>
    public static class SkeletonDiagnosticsService
    {
        public static SkeletonDiagnosticsResult Diagnose(string rootObjectName = "", string searchQuery = "")
        {
            var result = new SkeletonDiagnosticsResult();

            GameObject root = null;
            if (!string.IsNullOrEmpty(rootObjectName))
            {
                root = GameObject.Find(rootObjectName);
                if (root == null)
                {
                    result.success = false;
                    result.error = $"Root GameObject '{rootObjectName}' not found in scene.";
                    return result;
                }
            }
            else
            {
                var animator = UnityEngine.Object.FindAnyObjectByType<Animator>();
                if (animator != null) root = animator.gameObject;
                else
                {
                    var smr = UnityEngine.Object.FindAnyObjectByType<SkinnedMeshRenderer>();
                    if (smr != null && smr.rootBone != null) root = smr.rootBone.gameObject;
                }
            }

            if (root == null)
            {
                result.success = false;
                result.error = "No skeleton root or Animator found in active scene.";
                return result;
            }

            result.rootName = root.name;

            var allTransforms = root.GetComponentsInChildren<Transform>(true);
            result.totalBones = allTransforms.Length;

            var boneNameCounts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

            foreach (var t in allTransforms)
            {
                if (boneNameCounts.TryGetValue(t.name, out int count))
                {
                    boneNameCounts[t.name] = count + 1;
                    if (count == 1) result.duplicateBones.Add(t.name);
                }
                else
                {
                    boneNameCounts[t.name] = 1;
                }

                // Check MMD D-bone chain naming patterns (e.g. "_D", "D_", "d_")
                if (t.name.EndsWith("_D", StringComparison.OrdinalIgnoreCase) || t.name.StartsWith("D_", StringComparison.OrdinalIgnoreCase) || t.name.Contains("_D_"))
                {
                    result.mmdChains.Add(t.name);
                }

                // Search query matching
                if (!string.IsNullOrEmpty(searchQuery))
                {
                    if (t.name.IndexOf(searchQuery, StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        result.matchingBones.Add(t.name);
                    }
                }
            }

            result.hierarchy = BuildHierarchyNode(root.transform, root.name);
            result.success = true;
            return result;
        }

        private static BoneNode BuildHierarchyNode(Transform current, string currentPath)
        {
            var lp = current.localPosition;
            var lr = current.localEulerAngles;
            var ls = current.localScale;

            var node = new BoneNode
            {
                name = current.name,
                path = currentPath,
                localPosition = new float[] { lp.x, lp.y, lp.z },
                localRotation = new float[] { lr.x, lr.y, lr.z },
                localScale = new float[] { ls.x, ls.y, ls.z },
                childCount = current.childCount
            };

            for (int i = 0; i < current.childCount; i++)
            {
                var child = current.GetChild(i);
                node.children.Add(BuildHierarchyNode(child, $"{currentPath}/{child.name}"));
            }

            return node;
        }
    }
}
