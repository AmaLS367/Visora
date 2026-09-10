using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class PrefabComponentInfo
    {
        public string typeName;
        public bool isMissingScript;
    }

    [Serializable]
    public class PrefabObjectNode
    {
        public string relativePath;
        public string name;
        public int depth;
        public bool activeSelf;
        public List<PrefabComponentInfo> components = new List<PrefabComponentInfo>();
        public bool isNestedPrefabInstanceRoot;
        public string nestedSourceAssetPath;
    }

    [Serializable]
    public class PrefabNestedInstanceInfo
    {
        public string relativePath;
        public string name;
        public string sourceAssetPath;
        public string sourceGuid;
        public string connectionStatus;
    }

    [Serializable]
    public class PrefabInspectResult
    {
        public bool success;
        public string error;
        public string assetPath;
        public string prefabName;
        public string assetGuid;
        public string prefabKind;
        public string basePrefabPath;
        public string rootObjectName;
        public string rootConnectionStatus = ConnectionNotAnInstance;
        public List<PrefabObjectNode> hierarchy = new List<PrefabObjectNode>();
        public List<PrefabNestedInstanceInfo> nestedPrefabs = new List<PrefabNestedInstanceInfo>();
        public List<string> editTargetAssetPaths = new List<string>();
        public int totalObjectCount;
        public int totalComponentCount;
        public bool truncated;
        public List<string> warnings = new List<string>();

        internal const string ConnectionNotAnInstance = "not_an_instance";
    }

    /// <summary>
    /// Read-only inspection of Prefab assets. Prefabs are loaded into Unity's isolated prefab
    /// content scene and always unloaded again, so the user's active scene, its dirty state, the
    /// selection, and any open Prefab Stage are never touched.
    /// </summary>
    public static class PrefabInspectionService
    {
        internal const string ConnectionConnected = "connected";
        internal const string ConnectionMissingAsset = "missing_asset";
        internal const string ConnectionDisconnected = "disconnected";

        private const int DefaultMaxObjects = 200;

        /// <summary>
        /// Runs <paramref name="body"/> against the isolated contents of a Prefab asset.
        ///
        /// The unload lives in a finally block on purpose: LoadPrefabContents opens a hidden scene
        /// that survives an exception thrown by the caller, and a leaked prefab content scene stays
        /// in memory for the rest of the Editor session.
        /// </summary>
        internal static T WithPrefabContents<T>(string assetPath, Func<GameObject, T> body)
        {
            if (body == null) throw new ArgumentNullException(nameof(body));

            GameObject contents = null;
            try
            {
                contents = PrefabUtility.LoadPrefabContents(assetPath);
                return body(contents);
            }
            finally
            {
                if (contents != null)
                {
                    PrefabUtility.UnloadPrefabContents(contents);
                }
            }
        }

        public static PrefabInspectResult InspectPrefabAsset(string assetPath, int maxObjects)
        {
            string normalizedPath = (assetPath ?? "").Replace("\\", "/").Trim();
            var result = new PrefabInspectResult { assetPath = normalizedPath };
            int limit = maxObjects > 0 ? maxObjects : DefaultMaxObjects;

            if (string.IsNullOrEmpty(normalizedPath))
            {
                result.error = "Asset path is required.";
                return result;
            }

            if (EditorApplication.isPlaying)
            {
                result.error = "Prefab asset inspection requires Edit Mode; the Editor is in Play Mode.";
                return result;
            }

            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                result.error = "Unity is compiling or importing assets; retry once the Editor is idle.";
                return result;
            }

            try
            {
                var mainAsset = AssetDatabase.LoadMainAssetAtPath(normalizedPath);
                if (mainAsset == null)
                {
                    result.error = $"Asset not found at path: {normalizedPath}";
                    return result;
                }

                var assetType = PrefabUtility.GetPrefabAssetType(mainAsset);
                if (assetType == PrefabAssetType.MissingAsset || mainAsset.GetType().Name == "BrokenPrefabAsset")
                {
                    result.error =
                        $"Prefab asset at '{normalizedPath}' is broken: Unity reports its Prefab source as missing.";
                    return result;
                }

                if (assetType == PrefabAssetType.NotAPrefab || !(mainAsset is GameObject))
                {
                    result.error =
                        $"Asset at '{normalizedPath}' is not a Prefab asset (main asset type: {mainAsset.GetType().Name}).";
                    return result;
                }

                result.prefabKind = KindName(assetType);
                result.prefabName = System.IO.Path.GetFileNameWithoutExtension(normalizedPath);
                result.assetGuid = AssetDatabase.AssetPathToGUID(normalizedPath);

                if (assetType == PrefabAssetType.Model)
                {
                    var modelRoot = mainAsset as GameObject;
                    if (modelRoot == null)
                    {
                        result.error = $"Model asset at '{normalizedPath}' could not be loaded as a GameObject.";
                        return result;
                    }
                    return Collect(result, modelRoot, limit);
                }

                return WithPrefabContents(normalizedPath, contents => Collect(result, contents, limit));
            }
            catch (Exception ex)
            {
                result.success = false;
                result.hierarchy.Clear();
                result.nestedPrefabs.Clear();
                result.editTargetAssetPaths.Clear();
                result.error = $"Prefab asset inspection failed: {ex.Message}";
                return result;
            }
        }

        internal static bool IsEditablePrefabAsset(string path)
        {
            if (string.IsNullOrEmpty(path)) return false;
            if (!path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase)) return false;
            var main = AssetDatabase.LoadMainAssetAtPath(path);
            if (main == null) return false;
            var type = PrefabUtility.GetPrefabAssetType(main);
            return type == PrefabAssetType.Regular || type == PrefabAssetType.Variant;
        }

        internal static string KindName(PrefabAssetType assetType)
        {
            switch (assetType)
            {
                case PrefabAssetType.Regular: return "regular";
                case PrefabAssetType.Variant: return "variant";
                case PrefabAssetType.Model: return "model";
                default: return "unknown";
            }
        }

        private static PrefabInspectResult Collect(PrefabInspectResult result, GameObject contents, int limit)
        {
            if (contents == null)
            {
                result.success = false;
                result.error = $"Unity returned no Prefab contents for '{result.assetPath}'.";
                return result;
            }

            result.rootObjectName = contents.name;

            var editTargets = new HashSet<string>(StringComparer.Ordinal);
            if (IsEditablePrefabAsset(result.assetPath))
            {
                editTargets.Add(result.assetPath);
            }

            if (result.prefabKind == "variant")
            {
                if (PrefabUtility.IsAnyPrefabInstanceRoot(contents))
                {
                    string basePath = PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(contents);
                    bool missing = PrefabUtility.IsPrefabAssetMissing(contents);
                    if (missing || string.IsNullOrEmpty(basePath))
                    {
                        result.rootConnectionStatus = ConnectionMissingAsset;
                        result.warnings.Add(
                            "The base Prefab of this Variant is missing; only the Variant's own content is reported.");
                    }
                    else
                    {
                        result.rootConnectionStatus = ConnectionConnected;
                        result.basePrefabPath = basePath;
                        if (IsEditablePrefabAsset(basePath))
                        {
                            editTargets.Add(basePath);
                        }
                    }
                }
                else
                {
                    result.rootConnectionStatus = ConnectionMissingAsset;
                    result.warnings.Add(
                        "Unity reports this asset is a Prefab Variant, but its base Prefab connection could not be resolved.");
                }
            }
            else if (result.prefabKind == "model")
            {
                result.warnings.Add(
                    "Model Prefabs are imported from 3D model files and are read-only; they cannot be edited directly as Prefab assets.");
            }

            Traverse(result, contents.transform, "", 0, limit, editTargets, true);

            var sortedTargets = new List<string>(editTargets);
            sortedTargets.Sort(StringComparer.Ordinal);
            result.editTargetAssetPaths = sortedTargets;

            if (result.truncated)
            {
                result.warnings.Add(
                    "Prefab contains " + result.totalObjectCount.ToString(CultureInfo.InvariantCulture) +
                    " GameObjects; only the first " + limit.ToString(CultureInfo.InvariantCulture) +
                    " are listed. Raise PREFAB_MAX_HIERARCHY_NODES to see more.");
            }

            result.success = true;
            return result;
        }

        /// <summary>
        /// Depth-first walk in sibling order, so hierarchy, nested prefabs, and paths are stable
        /// across calls. Counters keep advancing past the emit limit so the reported totals describe
        /// the whole asset, not just the listed prefix. Duplicate sibling names are indexed so relative
        /// paths remain strictly unambiguous.
        /// </summary>
        private static void Traverse(
            PrefabInspectResult result,
            Transform current,
            string relativePath,
            int depth,
            int limit,
            HashSet<string> editTargets,
            bool isContentsRoot)
        {
            result.totalObjectCount++;

            var components = current.GetComponents<Component>();
            result.totalComponentCount += components.Length;

            bool isNestedRoot = !isContentsRoot && PrefabUtility.IsAnyPrefabInstanceRoot(current.gameObject);
            string nestedSourcePath = null;
            if (isNestedRoot)
            {
                nestedSourcePath = RecordNestedInstance(result, current, relativePath, limit, editTargets);
            }

            if (result.hierarchy.Count < limit)
            {
                var node = new PrefabObjectNode
                {
                    relativePath = relativePath,
                    name = current.name,
                    depth = depth,
                    activeSelf = current.gameObject.activeSelf,
                    isNestedPrefabInstanceRoot = isNestedRoot,
                    nestedSourceAssetPath = nestedSourcePath
                };

                for (int i = 0; i < components.Length; i++)
                {
                    var component = components[i];
                    node.components.Add(new PrefabComponentInfo
                    {
                        typeName = component == null ? "MissingScript" : component.GetType().Name,
                        isMissingScript = component == null
                    });
                }

                result.hierarchy.Add(node);
            }
            else
            {
                result.truncated = true;
            }

            var children = HierarchyPaths.Children(current);
            var childSegments = HierarchyPaths.SiblingSegments(children);
            for (int i = 0; i < children.Count; i++)
            {
                var child = children[i];
                string childSegment = childSegments[i];
                if (string.Equals(childSegment, HierarchyPaths.Indexed(child.name, 0), StringComparison.Ordinal))
                {
                    result.warnings.Add(
                        $"GameObject '{current.name}' has multiple children named '{child.name}'; paths are disambiguated with indices like '{childSegment}'.");
                }

                string childPath = relativePath.Length == 0 ? childSegment : relativePath + "/" + childSegment;
                Traverse(result, child, childPath, depth + 1, limit, editTargets, false);
            }
        }

        private static string RecordNestedInstance(
            PrefabInspectResult result,
            Transform current,
            string relativePath,
            int limit,
            HashSet<string> editTargets)
        {
            // Deliberately not PrefabUtility.GetPrefabInstanceStatus: its Disconnected member is
            // obsolete in current Unity, and the two facts that matter here - does the source asset
            // still resolve, and to what path - are available directly and without deprecation.
            bool missing = PrefabUtility.IsPrefabAssetMissing(current.gameObject);
            string sourcePath = missing ? null : PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(current.gameObject);

            string status;
            if (missing)
            {
                status = ConnectionMissingAsset;
            }
            else if (string.IsNullOrEmpty(sourcePath))
            {
                status = ConnectionDisconnected;
            }
            else
            {
                status = ConnectionConnected;
            }

            string sourceGuid = null;
            if (!string.IsNullOrEmpty(sourcePath))
            {
                sourceGuid = AssetDatabase.AssetPathToGUID(sourcePath);
                if (IsEditablePrefabAsset(sourcePath))
                {
                    editTargets.Add(sourcePath);
                }
                else
                {
                    result.warnings.Add(
                        $"Nested instance '{current.name}' is from model asset '{sourcePath}'; model assets cannot be targeted for prefab edits.");
                }
            }
            else
            {
                result.warnings.Add(
                    $"Nested Prefab instance '{current.name}' has no resolvable source asset; it cannot be an edit target.");
            }

            if (result.nestedPrefabs.Count < limit)
            {
                result.nestedPrefabs.Add(new PrefabNestedInstanceInfo
                {
                    relativePath = relativePath,
                    name = current.name,
                    sourceAssetPath = sourcePath,
                    sourceGuid = sourceGuid,
                    connectionStatus = status
                });
            }
            else
            {
                result.truncated = true;
            }

            return sourcePath;
        }
    }
}
