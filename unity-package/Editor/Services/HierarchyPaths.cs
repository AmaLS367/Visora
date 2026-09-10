using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Visora.Editor.Services
{
    [Serializable]
    public class HierarchyPathCandidate
    {
        public string scenePath;
        public string hierarchyPath;
    }

    /// <summary>
    /// Outcome of resolving a hierarchy path across the loaded scenes: exactly one target, or an
    /// explicit error with the candidates an agent can retry with.
    /// </summary>
    internal sealed class HierarchyResolution
    {
        public GameObject target;
        public string error;
        public List<HierarchyPathCandidate> candidates = new List<HierarchyPathCandidate>();
    }

    /// <summary>
    /// The one canonical hierarchy-path convention shared by every prefab service.
    ///
    /// A segment is the GameObject name when it is unique among its siblings, and
    /// <c>Name[k]</c> (k = 0-based occurrence among same-name siblings, in sibling order) when
    /// several siblings share it. Paths are relative to a root ('' is the root itself) and contain
    /// no leading slash. Unlike <c>GameObject.Find</c>, resolution never silently picks one of
    /// several matches and never falls back to a terminal-name search.
    /// </summary>
    internal static class HierarchyPaths
    {
        private const int MaxCandidates = 20;

        internal static string Indexed(string name, int occurrence)
        {
            return name + "[" + occurrence.ToString(CultureInfo.InvariantCulture) + "]";
        }

        /// <summary>Canonical segments for an ordered sibling list, parallel to it.</summary>
        internal static string[] SiblingSegments(IList<Transform> siblings)
        {
            var counts = new Dictionary<string, int>(StringComparer.Ordinal);
            for (int i = 0; i < siblings.Count; i++)
            {
                counts.TryGetValue(siblings[i].name, out int count);
                counts[siblings[i].name] = count + 1;
            }

            var occurrences = new Dictionary<string, int>(StringComparer.Ordinal);
            var segments = new string[siblings.Count];
            for (int i = 0; i < siblings.Count; i++)
            {
                string name = siblings[i].name;
                if (counts[name] > 1)
                {
                    occurrences.TryGetValue(name, out int occurrence);
                    occurrences[name] = occurrence + 1;
                    segments[i] = Indexed(name, occurrence);
                }
                else
                {
                    segments[i] = name;
                }
            }
            return segments;
        }

        internal static List<Transform> Children(Transform parent)
        {
            if (parent == null) return new List<Transform>();
            var children = new List<Transform>(parent.childCount);
            for (int i = 0; i < parent.childCount; i++)
            {
                var child = parent.GetChild(i);
                if (child != null)
                {
                    children.Add(child);
                }
            }
            return children;
        }

        internal static List<Transform> SceneRoots(Scene scene)
        {
            var roots = new List<Transform>();
            if (!scene.IsValid() || !scene.isLoaded) return roots;
            foreach (var root in scene.GetRootGameObjects())
            {
                if (root != null)
                {
                    roots.Add(root.transform);
                }
            }
            return roots;
        }

        /// <summary>Canonical segment of one transform among its siblings (scene roots for a scene root).</summary>
        internal static string Segment(Transform transform)
        {
            List<Transform> siblings;
            if (transform.parent != null)
            {
                siblings = Children(transform.parent);
            }
            else if (transform.gameObject.scene.IsValid())
            {
                siblings = SceneRoots(transform.gameObject.scene);
            }
            else
            {
                return transform.name;
            }

            int index = siblings.IndexOf(transform);
            return index < 0 ? transform.name : SiblingSegments(siblings)[index];
        }

        /// <summary>
        /// Path of <paramref name="target"/> relative to <paramref name="root"/>: '' for the root
        /// itself, null when the target is not inside the root's hierarchy.
        /// </summary>
        internal static string RelativePath(Transform root, Transform target)
        {
            if (root == null || target == null) return null;
            if (target == root) return "";

            var segments = new List<string>();
            var current = target;
            while (current != null && current != root)
            {
                segments.Add(Segment(current));
                current = current.parent;
            }
            if (current != root) return null;

            segments.Reverse();
            return string.Join("/", segments);
        }

        /// <summary>Full canonical path of a transform from its scene (or asset) root, root segment included.</summary>
        internal static string RootedPath(Transform target)
        {
            if (target == null) return null;
            var segments = new List<string>();
            for (var current = target; current != null; current = current.parent)
            {
                segments.Add(Segment(current));
            }
            segments.Reverse();
            return string.Join("/", segments);
        }

        /// <summary>Scene identity used in results: its asset path, or its name for an unsaved scene.</summary>
        internal static string SceneIdentity(Scene scene)
        {
            if (!scene.IsValid()) return "";
            return string.IsNullOrEmpty(scene.path) ? scene.name : scene.path;
        }

        /// <summary>
        /// Resolves a root-anchored path ('Root/Child/Leaf', segments optionally indexed as
        /// 'Name[k]') across every loaded scene, optionally restricted to the scene whose path or
        /// name equals <paramref name="sceneFilter"/>. Missing and ambiguous paths are errors.
        /// </summary>
        internal static HierarchyResolution ResolveInLoadedScenes(string path, string sceneFilter)
        {
            var resolution = new HierarchyResolution();
            string normalized = (path ?? "").Trim().Trim('/');
            if (normalized.Length == 0)
            {
                resolution.error = "Hierarchy path is required.";
                return resolution;
            }

            string[] segments = normalized.Split('/');
            for (int i = 0; i < segments.Length; i++)
            {
                if (segments[i].Length == 0)
                {
                    resolution.error = $"Hierarchy path '{normalized}' contains an empty segment.";
                    return resolution;
                }
            }

            string filter = string.IsNullOrWhiteSpace(sceneFilter) ? null : sceneFilter.Replace("\\", "/").Trim().TrimStart('/');
            var scenes = new List<Scene>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                var scene = SceneManager.GetSceneAt(i);
                if (!scene.IsValid() || !scene.isLoaded) continue;
                string scenePath = !string.IsNullOrEmpty(scene.path) ? scene.path.Replace("\\", "/").TrimStart('/') : "";
                if (filter != null &&
                    !string.Equals(scenePath, filter, StringComparison.Ordinal) &&
                    !string.Equals(scene.name, filter, StringComparison.Ordinal))
                {
                    continue;
                }
                scenes.Add(scene);
            }

            if (scenes.Count == 0)
            {
                resolution.error = filter == null
                    ? "No scene is loaded."
                    : $"Scene '{sceneFilter.Trim()}' is not loaded.";
                return resolution;
            }

            var matches = new List<Transform>();
            int deepestMatchedSegments = 0;
            string deepestPrefix = null;
            foreach (var scene in scenes)
            {
                var level = MatchSegment(SceneRoots(scene), segments[0]);
                for (int depth = 1; depth < segments.Length && level.Count > 0; depth++)
                {
                    if (depth > deepestMatchedSegments)
                    {
                        deepestMatchedSegments = depth;
                        deepestPrefix = string.Join("/", segments, 0, depth);
                    }
                    var next = new List<Transform>();
                    foreach (var parent in level)
                    {
                        next.AddRange(MatchSegment(Children(parent), segments[depth]));
                    }
                    level = next;
                }
                matches.AddRange(level);
            }

            if (matches.Count == 0)
            {
                resolution.error = deepestPrefix == null
                    ? $"No GameObject at hierarchy path '{normalized}' in the loaded scenes."
                    : $"No GameObject at hierarchy path '{normalized}' in the loaded scenes; the deepest existing prefix is '{deepestPrefix}'.";
                return resolution;
            }

            if (matches.Count > 1)
            {
                for (int i = 0; i < matches.Count && i < MaxCandidates; i++)
                {
                    resolution.candidates.Add(new HierarchyPathCandidate
                    {
                        scenePath = SceneIdentity(matches[i].gameObject.scene),
                        hierarchyPath = RootedPath(matches[i])
                    });
                }
                resolution.error =
                    $"Hierarchy path '{normalized}' is ambiguous: it matches {matches.Count.ToString(CultureInfo.InvariantCulture)} GameObjects. " +
                    "Retry with one of the indexed candidate paths (and scene_path when they live in different scenes).";
                return resolution;
            }

            resolution.target = matches[0].gameObject;
            return resolution;
        }

        /// <summary>
        /// Siblings matching one segment, either literally by name or by canonical (indexed)
        /// segment. Both readings are kept, so a literal 'Arm[1]' next to two 'Arm' siblings is
        /// reported as ambiguous instead of silently choosing one.
        /// </summary>
        private static List<Transform> MatchSegment(List<Transform> siblings, string segment)
        {
            var result = new List<Transform>();
            var canonical = SiblingSegments(siblings);
            for (int i = 0; i < siblings.Count; i++)
            {
                if (string.Equals(siblings[i].name, segment, StringComparison.Ordinal) ||
                    string.Equals(canonical[i], segment, StringComparison.Ordinal))
                {
                    result.Add(siblings[i]);
                }
            }
            return result;
        }
    }
}
