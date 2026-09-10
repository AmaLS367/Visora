using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class PrefabObjectReferenceInfo
    {
        public bool isNull;
        public string typeName;
        public string name;
        public string assetPath;
        public string assetGuid;
        public long? localFileId;
        public string scenePath;
        public string hierarchyPath;
    }

    [Serializable]
    public class PrefabPropertyValueInfo
    {
        public string kind;
        public object value;
        public PrefabObjectReferenceInfo objectReference;
    }

    [Serializable]
    public class PrefabOverrideInfo
    {
        public string overrideId;
        public string category;
        public string objectPath;
        public string sourceObjectPath;
        public string componentType;
        public int? componentOrdinal;
        public string propertyPath;
        public PrefabPropertyValueInfo sourceValue;
        public PrefabPropertyValueInfo instanceValue;
        public bool isDefaultOverride;
        public List<string> targetAssetPaths = new List<string>();
        public string recommendedTargetAssetPath;
        public bool applicable;
        public string notApplicableReason;
        public bool idCollision;
        public string description;

        // Identity inputs that are not part of the wire format (non-public, so VisoraJson skips them).
        internal string ComponentTypeFullName;
        internal int ComponentOrdinalForIdentity;
        internal string CanonicalIdentity;
    }

    [Serializable]
    public class PrefabOverrideCounts
    {
        public int modifiedProperty;
        public int addedComponent;
        public int removedComponent;
        public int addedGameObject;
        public int removedGameObject;
    }

    [Serializable]
    public class PrefabOverridesInspectResult
    {
        public bool success;
        public string error;
        public string instancePath;
        public string scenePath;
        public string instanceRootPath;
        public string outermostInstanceRootPath;
        public string scope;
        public string sourceAssetPath;
        public string sourceGuid;
        public string prefabKind = "unknown";
        public string connectionStatus = PrefabInspectResult.ConnectionNotAnInstance;
        public bool includeDefaultOverrides;
        public int totalOverrideCount;
        public PrefabOverrideCounts overrideCounts = new PrefabOverrideCounts();
        public int excludedDefaultOverrideCount;
        public bool truncated;
        public List<PrefabOverrideInfo> overrides = new List<PrefabOverrideInfo>();
        public List<HierarchyPathCandidate> pathCandidates = new List<HierarchyPathCandidate>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Read-only, typed diff between a Prefab instance in a loaded scene and its source Prefab asset.
    ///
    /// Everything comes from Unity's own override inspection APIs (GetObjectOverrides,
    /// GetPropertyModifications + IsDefaultOverride, GetAdded/RemovedComponents,
    /// GetAdded/RemovedGameObjects). Nothing is applied, reverted, saved, selected, or created: the
    /// only objects touched are SerializedObject readers, which are disposed before returning.
    /// </summary>
    public static class PrefabOverrideInspectionService
    {
        internal const string CategoryModifiedProperty = "modified_property";
        internal const string CategoryAddedComponent = "added_component";
        internal const string CategoryRemovedComponent = "removed_component";
        internal const string CategoryAddedGameObject = "added_game_object";
        internal const string CategoryRemovedGameObject = "removed_game_object";

        internal const string ScopeNearest = "nearest";
        internal const string ScopeOutermost = "outermost";

        internal const string IdPrefix = "ovr_";
        private const string IdentityVersion = "v1";

        private const int DefaultMaxOverrides = 200;
        private const int MaxOverridesCeiling = 1000;
        private const int MaxSourceChainDepth = 64;

        private static readonly string[] CategoryOrder =
        {
            CategoryModifiedProperty,
            CategoryAddedComponent,
            CategoryRemovedComponent,
            CategoryAddedGameObject,
            CategoryRemovedGameObject
        };

        public static PrefabOverridesInspectResult InspectPrefabOverrides(
            string instancePath,
            string scenePath,
            bool includeDefaultOverrides,
            string scope,
            int maxOverrides)
        {
            string normalizedPath = (instancePath ?? "").Trim().Trim('/');
            string normalizedScope = string.IsNullOrWhiteSpace(scope) ? ScopeNearest : scope.Trim();
            var result = new PrefabOverridesInspectResult
            {
                instancePath = normalizedPath,
                scope = normalizedScope,
                includeDefaultOverrides = includeDefaultOverrides
            };
            int limit = maxOverrides > 0 ? Math.Min(maxOverrides, MaxOverridesCeiling) : DefaultMaxOverrides;

            if (normalizedPath.Length == 0)
            {
                result.error = "Instance path is required.";
                return result;
            }

            if (normalizedScope != ScopeNearest && normalizedScope != ScopeOutermost)
            {
                result.error = $"Unknown scope '{normalizedScope}'; expected 'nearest' or 'outermost'.";
                return result;
            }

            if (EditorApplication.isPlaying)
            {
                result.error = "Prefab override inspection requires Edit Mode; the Editor is in Play Mode.";
                return result;
            }

            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                result.error = "Unity is compiling or importing assets; retry once the Editor is idle.";
                return result;
            }

            var readers = new SerializedObjectCache();
            try
            {
                return Inspect(result, normalizedPath, scenePath, limit, readers);
            }
            catch (Exception ex)
            {
                // A partial diff must never look complete.
                result.success = false;
                result.overrides.Clear();
                result.totalOverrideCount = 0;
                result.overrideCounts = new PrefabOverrideCounts();
                result.excludedDefaultOverrideCount = 0;
                result.truncated = false;
                result.error = $"Prefab override inspection failed: {ex.Message}";
                return result;
            }
            finally
            {
                readers.Dispose();
            }
        }

        private static PrefabOverridesInspectResult Inspect(
            PrefabOverridesInspectResult result,
            string path,
            string sceneFilter,
            int limit,
            SerializedObjectCache readers)
        {
            var resolution = HierarchyPaths.ResolveInLoadedScenes(path, sceneFilter);
            if (resolution.target == null)
            {
                result.error = resolution.error;
                result.pathCandidates = resolution.candidates;
                return result;
            }

            var target = resolution.target;
            result.scenePath = HierarchyPaths.SceneIdentity(target.scene);

            // An added GameObject is not part of the instance itself, but it lives inside one.
            var anchor = target.transform;
            while (anchor != null && !PrefabUtility.IsPartOfPrefabInstance(anchor.gameObject))
            {
                anchor = anchor.parent;
            }
            if (anchor == null)
            {
                result.error = $"GameObject '{path}' is not part of a Prefab instance.";
                return result;
            }
            if (anchor != target.transform)
            {
                result.warnings.Add(
                    $"'{path}' is not itself part of a Prefab instance (it is an added GameObject); inspecting the instance that contains it.");
            }

            var nearestRoot = PrefabUtility.GetNearestPrefabInstanceRoot(anchor.gameObject);
            var outermostRoot = PrefabUtility.GetOutermostPrefabInstanceRoot(anchor.gameObject);
            var root = result.scope == ScopeOutermost ? outermostRoot : nearestRoot;
            if (root == null)
            {
                result.error = $"Unity could not resolve the {result.scope} Prefab instance root of '{path}'.";
                return result;
            }

            result.instanceRootPath = HierarchyPaths.RootedPath(root.transform);
            result.outermostInstanceRootPath = outermostRoot != null
                ? HierarchyPaths.RootedPath(outermostRoot.transform)
                : result.instanceRootPath;

            if (PrefabUtility.IsPrefabAssetMissing(root))
            {
                result.connectionStatus = PrefabInspectionService.ConnectionMissingAsset;
                result.error =
                    $"The source Prefab asset of instance '{result.instanceRootPath}' is missing; Unity cannot compute its overrides.";
                return result;
            }

            string sourcePath = PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(root);
            if (string.IsNullOrEmpty(sourcePath))
            {
                result.connectionStatus = PrefabInspectionService.ConnectionDisconnected;
                result.error =
                    $"Prefab instance '{result.instanceRootPath}' is not connected to a source Prefab asset; Unity cannot compute its overrides.";
                return result;
            }

            result.connectionStatus = PrefabInspectionService.ConnectionConnected;
            result.sourceAssetPath = sourcePath;
            result.sourceGuid = AssetDatabase.AssetPathToGUID(sourcePath);
            result.prefabKind = PrefabInspectionService.KindName(PrefabUtility.GetPrefabAssetType(root));
            if (result.prefabKind == "model")
            {
                result.warnings.Add(
                    $"'{sourcePath}' is a Model Prefab imported from a model file; it is immutable, so overrides can only target an enclosing editable Prefab, if any.");
            }

            var stage = PrefabStageUtility.GetCurrentPrefabStage();
            if (stage != null && stage.scene.isDirty)
            {
                result.warnings.Add(
                    $"The open Prefab Stage for '{stage.assetPath}' has unsaved changes; overrides are computed against the Prefab assets as saved.");
            }

            var context = new InspectionContext(result, root, outermostRoot != null ? outermostRoot : root, readers);
            var all = new List<PrefabOverrideInfo>();
            CollectPropertyOverrides(context, all);
            CollectAddedComponents(context, all);
            CollectRemovedComponents(context, all);
            CollectAddedGameObjects(context, all);
            CollectRemovedGameObjects(context, all);

            foreach (var entry in all)
            {
                entry.CanonicalIdentity = CanonicalIdentity(result, entry);
            }
            all.Sort(CompareOverrides);
            AssignIds(result, all);

            foreach (var entry in all)
            {
                if (entry.isDefaultOverride && !result.includeDefaultOverrides)
                {
                    result.excludedDefaultOverrideCount++;
                    continue;
                }

                result.totalOverrideCount++;
                CountCategory(result.overrideCounts, entry.category);
                if (result.overrides.Count < limit)
                {
                    result.overrides.Add(entry);
                }
                else
                {
                    result.truncated = true;
                }
            }

            if (result.truncated)
            {
                result.warnings.Add(
                    "Instance has " + result.totalOverrideCount.ToString(CultureInfo.InvariantCulture) +
                    " overrides; only the first " + limit.ToString(CultureInfo.InvariantCulture) +
                    " are listed. Raise max_overrides (up to " + MaxOverridesCeiling.ToString(CultureInfo.InvariantCulture) +
                    ") to see more.");
            }

            result.success = true;
            return result;
        }

        // ------------------------------------------------------------------------------------
        // Collection, one Unity inspection API per category
        // ------------------------------------------------------------------------------------

        private static void CollectPropertyOverrides(InspectionContext context, List<PrefabOverrideInfo> output)
        {
            // Objects Unity itself reports as carrying overrides (default ones included; filtered later).
            var overridden = new HashSet<UnityEngine.Object>();
            foreach (var handle in context.OverrideHandles)
            {
                foreach (var objectOverride in PrefabUtility.GetObjectOverrides(handle, true))
                {
                    var instanceObject = objectOverride.instanceObject;
                    if (instanceObject != null && context.InScope(TransformOf(instanceObject)))
                    {
                        overridden.Add(instanceObject);
                    }
                }
            }

            // Scene property modifications target the instance's immediate source objects.
            var bySource = new Dictionary<UnityEngine.Object, List<UnityEngine.Object>>();
            foreach (var instanceObject in overridden)
            {
                var source = PrefabUtility.GetCorrespondingObjectFromSource(instanceObject);
                if (source != null)
                {
                    if (!bySource.TryGetValue(source, out var list))
                    {
                        list = new List<UnityEngine.Object>();
                        bySource[source] = list;
                    }
                    list.Add(instanceObject);
                }
            }

            var seen = new HashSet<(UnityEngine.Object, string)>();
            int skipped = 0;
            foreach (var handle in context.OverrideHandles)
            {
                var modifications = PrefabUtility.GetPropertyModifications(handle);
                if (modifications == null) continue;

                foreach (var modification in modifications)
                {
                    if (modification == null || modification.target == null) continue;
                    if (!bySource.TryGetValue(modification.target, out var instanceObjects)) continue;

                    foreach (var instanceObject in instanceObjects)
                    {
                        if (!seen.Add((instanceObject, modification.propertyPath))) continue;

                        var property = context.Readers.Get(instanceObject).FindProperty(modification.propertyPath);
                        if (property == null || !property.prefabOverride)
                        {
                            // A stale modification (value equals the source again) or one without a
                            // serialized property: Unity's own Overrides window hides these too.
                            skipped++;
                            continue;
                        }

                        var entry = NewOverride(context, CategoryModifiedProperty, instanceObject);
                        entry.propertyPath = modification.propertyPath;
                        entry.isDefaultOverride = PrefabUtility.IsDefaultOverride(modification);
                        entry.instanceValue = ReadValue(property, modification.value);

                        var sourceProperty = context.Readers.Get(modification.target).FindProperty(modification.propertyPath);
                        entry.sourceValue = sourceProperty != null ? ReadValue(sourceProperty, null) : null;

                        var referenced = property.propertyType == SerializedPropertyType.ObjectReference
                            ? property.objectReferenceValue
                            : null;
                        ResolveTargets(context, entry, SourceChain(instanceObject, false), referenced);
                        entry.description =
                            $"{Subject(entry)}: '{entry.propertyPath}' changed from {ValueText(entry.sourceValue)} to {ValueText(entry.instanceValue)}.";
                        output.Add(entry);
                    }
                }
            }

            if (skipped > 0)
            {
                context.Result.warnings.Add(
                    "Skipped " + skipped.ToString(CultureInfo.InvariantCulture) +
                    " property modification(s) that no longer differ from the source or do not map to a serialized property.");
            }
        }

        private static void CollectAddedComponents(InspectionContext context, List<PrefabOverrideInfo> output)
        {
            var seen = new HashSet<Component>();
            foreach (var handle in context.OverrideHandles)
            {
                foreach (var added in PrefabUtility.GetAddedComponents(handle))
                {
                    var component = added.instanceComponent;
                    if (component == null || !seen.Add(component) || !context.InScope(component.transform)) continue;

                    var entry = NewOverride(context, CategoryAddedComponent, component);
                    ResolveTargets(context, entry, SourceChain(component.gameObject, false), null);
                    entry.description = $"Added component {entry.componentType} on {DisplayPath(entry.objectPath)}.";
                    output.Add(entry);
                }
            }
        }

        private static void CollectRemovedComponents(InspectionContext context, List<PrefabOverrideInfo> output)
        {
            var seen = new HashSet<Component>();
            foreach (var handle in context.OverrideHandles)
            {
                foreach (var removed in PrefabUtility.GetRemovedComponents(handle))
                {
                    var assetComponent = removed.assetComponent;
                    var holder = removed.containingInstanceGameObject;
                    if (assetComponent == null || holder == null || !seen.Add(assetComponent) ||
                        !context.InScope(holder.transform))
                    {
                        continue;
                    }

                    var entry = new PrefabOverrideInfo
                    {
                        category = CategoryRemovedComponent,
                        objectPath = HierarchyPaths.RelativePath(context.Root.transform, holder.transform),
                        sourceObjectPath = SourcePathInScopeAsset(context, assetComponent.gameObject)
                    };
                    SetComponentIdentity(entry, assetComponent);
                    ResolveTargets(context, entry, SourceChain(assetComponent, true), null);
                    entry.description = $"Removed component {entry.componentType} from {DisplayPath(entry.objectPath)}.";
                    output.Add(entry);
                }
            }
        }

        private static void CollectAddedGameObjects(InspectionContext context, List<PrefabOverrideInfo> output)
        {
            var seen = new HashSet<GameObject>();
            foreach (var handle in context.OverrideHandles)
            {
                foreach (var added in PrefabUtility.GetAddedGameObjects(handle))
                {
                    var gameObject = added.instanceGameObject;
                    if (gameObject == null || !seen.Add(gameObject) || !context.InScope(gameObject.transform)) continue;

                    var parent = gameObject.transform.parent;
                    var entry = new PrefabOverrideInfo
                    {
                        category = CategoryAddedGameObject,
                        objectPath = HierarchyPaths.RelativePath(context.Root.transform, gameObject.transform)
                    };
                    var chain = parent != null ? SourceChain(parent.gameObject, false) : new List<UnityEngine.Object>();
                    ResolveTargets(context, entry, chain, null);
                    string parentPath = parent != null ? HierarchyPaths.RelativePath(context.Root.transform, parent) : null;
                    entry.description =
                        $"Added GameObject '{gameObject.name}' under {DisplayPath(parentPath)} at sibling index {added.siblingIndex.ToString(CultureInfo.InvariantCulture)}.";
                    output.Add(entry);
                }
            }
        }

        private static void CollectRemovedGameObjects(InspectionContext context, List<PrefabOverrideInfo> output)
        {
            var seen = new HashSet<GameObject>();
            foreach (var handle in context.OverrideHandles)
            {
                foreach (var removed in PrefabUtility.GetRemovedGameObjects(handle))
                {
                    var assetGameObject = removed.assetGameObject;
                    var parent = removed.parentOfRemovedGameObjectInInstance;
                    if (assetGameObject == null || parent == null || !seen.Add(assetGameObject) ||
                        !context.InScope(parent.transform))
                    {
                        continue;
                    }

                    var entry = new PrefabOverrideInfo
                    {
                        category = CategoryRemovedGameObject,
                        objectPath = HierarchyPaths.RelativePath(context.Root.transform, parent.transform),
                        sourceObjectPath = SourcePathInScopeAsset(context, assetGameObject)
                    };
                    ResolveTargets(context, entry, SourceChain(assetGameObject, true), null);
                    entry.description =
                        $"Removed GameObject '{assetGameObject.name}' from under {DisplayPath(entry.objectPath)}.";
                    output.Add(entry);
                }
            }
        }

        // ------------------------------------------------------------------------------------
        // Identity, targets, values
        // ------------------------------------------------------------------------------------

        private static PrefabOverrideInfo NewOverride(InspectionContext context, string category, UnityEngine.Object instanceObject)
        {
            var gameObject = GameObjectOf(instanceObject);
            var entry = new PrefabOverrideInfo
            {
                category = category,
                objectPath = gameObject != null
                    ? HierarchyPaths.RelativePath(context.Root.transform, gameObject.transform)
                    : null,
                sourceObjectPath = gameObject != null ? SourcePathInScopeAsset(context, gameObject) : null
            };
            if (instanceObject is Component component)
            {
                SetComponentIdentity(entry, component);
            }
            return entry;
        }

        /// <summary>
        /// Component type plus its 0-based position among components of exactly that type on the
        /// same GameObject. The ordinal is always part of the identity but only surfaced when the
        /// GameObject really carries several components of the type.
        /// </summary>
        private static void SetComponentIdentity(PrefabOverrideInfo entry, Component component)
        {
            if (component == null)
            {
                entry.componentType = "MissingScript";
                entry.ComponentTypeFullName = "MissingScript";
                entry.ComponentOrdinalForIdentity = 0;
                entry.componentOrdinal = null;
                return;
            }

            Type type;
            try
            {
                type = component.GetType();
            }
            catch
            {
                entry.componentType = "MissingScript";
                entry.ComponentTypeFullName = "MissingScript";
                entry.ComponentOrdinalForIdentity = 0;
                entry.componentOrdinal = null;
                return;
            }

            entry.componentType = type.Name;
            entry.ComponentTypeFullName = type.FullName ?? type.Name;

            int ordinal = 0;
            int count = 0;
            try
            {
                var go = component.gameObject;
                if (go != null)
                {
                    foreach (var candidate in go.GetComponents<Component>())
                    {
                        if (candidate == null || candidate.GetType() != type) continue;
                        if (candidate == component) ordinal = count;
                        count++;
                    }
                }
            }
            catch
            {
                // Component or GameObject is broken; retain default ordinal
            }
            entry.ComponentOrdinalForIdentity = ordinal;
            entry.componentOrdinal = count > 1 ? ordinal : (int?)null;
        }

        /// <summary>
        /// The Prefab asset objects an override could be applied to, from the instance's immediate
        /// source inwards (outer Prefab, then nested/base Prefabs, down to the asset that
        /// introduced the object). Asset objects (removed components/GameObjects) start at themselves.
        /// </summary>
        private static List<UnityEngine.Object> SourceChain(UnityEngine.Object start, bool includeStart)
        {
            var chain = new List<UnityEngine.Object>();
            var current = includeStart ? start : PrefabUtility.GetCorrespondingObjectFromSource(start);
            for (int depth = 0; current != null && depth < MaxSourceChainDepth; depth++)
            {
                chain.Add(current);
                current = PrefabUtility.GetCorrespondingObjectFromSource(current);
            }
            return chain;
        }

        private static UnityEngine.Object CorrespondingAtPath(UnityEngine.Object start, string assetPath)
        {
            var current = start;
            for (int depth = 0; current != null && depth < MaxSourceChainDepth; depth++)
            {
                if (string.Equals(AssetDatabase.GetAssetPath(current), assetPath, StringComparison.Ordinal))
                {
                    return current;
                }
                current = PrefabUtility.GetCorrespondingObjectFromSource(current);
            }
            return null;
        }

        private static string SourcePathInScopeAsset(InspectionContext context, UnityEngine.Object instanceOrAssetObject)
        {
            var level = CorrespondingAtPath(instanceOrAssetObject, context.Result.sourceAssetPath);
            var transform = TransformOf(level);
            return transform != null ? HierarchyPaths.RelativePath(transform.root, transform) : null;
        }

        /// <summary>
        /// Filters the source chain down to assets Unity could really write this override into and
        /// decides applicability. Never assumes the outermost Prefab is the right target.
        /// </summary>
        private static void ResolveTargets(
            InspectionContext context,
            PrefabOverrideInfo entry,
            List<UnityEngine.Object> chain,
            UnityEngine.Object referenced)
        {
            var rejections = new List<string>();
            foreach (var level in chain)
            {
                string assetPath = AssetDatabase.GetAssetPath(level);
                if (string.IsNullOrEmpty(assetPath) || entry.targetAssetPaths.Contains(assetPath)) continue;

                if (PrefabUtility.IsPartOfModelPrefab(level))
                {
                    rejections.Add($"'{assetPath}' is a Model Prefab, which is imported from a model file and cannot be modified.");
                    continue;
                }
                if (PrefabUtility.IsPartOfImmutablePrefab(level) || !context.IsEditable(assetPath))
                {
                    rejections.Add($"'{assetPath}' is immutable (for example inside a read-only package).");
                    continue;
                }
                if (referenced != null && !EditorUtility.IsPersistent(referenced) &&
                    CorrespondingAtPath(referenced, assetPath) == null)
                {
                    rejections.Add(
                        $"'{assetPath}' cannot store the reference to scene object '{referenced.name}', which has no counterpart in that asset.");
                    continue;
                }
                entry.targetAssetPaths.Add(assetPath);
            }

            if (entry.isDefaultOverride)
            {
                entry.targetAssetPaths.Clear();
                entry.recommendedTargetAssetPath = null;
                entry.applicable = false;
                entry.notApplicableReason =
                    "Unity classifies this as a default override (instance placement or naming of the Prefab root), which is never applied to a Prefab asset.";
                return;
            }

            if (entry.targetAssetPaths.Count == 0)
            {
                entry.applicable = false;
                entry.notApplicableReason = rejections.Count > 0
                    ? "No Prefab asset can accept this override: " + string.Join(" ", rejections)
                    : "Unity reports no source Prefab asset for this override.";
                return;
            }

            entry.applicable = true;
            entry.recommendedTargetAssetPath = entry.targetAssetPaths.Contains(context.Result.sourceAssetPath)
                ? context.Result.sourceAssetPath
                : entry.targetAssetPaths[0];
        }

        private static string CanonicalIdentity(PrefabOverridesInspectResult result, PrefabOverrideInfo entry)
        {
            string source = string.IsNullOrEmpty(result.sourceGuid) ? result.sourceAssetPath : result.sourceGuid;
            var builder = new StringBuilder();
            builder.Append(IdentityVersion);
            AppendField(builder, "category", entry.category);
            AppendField(builder, "source", source);
            AppendField(builder, "context", result.scope + "@" + result.scenePath + ":" + result.instanceRootPath);
            AppendField(builder, "object", entry.objectPath);
            AppendField(builder, "sourceObject", entry.sourceObjectPath);
            AppendField(builder, "component", entry.ComponentTypeFullName);
            AppendField(builder, "ordinal",
                entry.ComponentTypeFullName == null ? null : entry.ComponentOrdinalForIdentity.ToString(CultureInfo.InvariantCulture));
            AppendField(builder, "property", entry.propertyPath);
            return builder.ToString();
        }

        /// <summary>One newline-separated 'key=value' field; null is encoded distinctly from ''.</summary>
        private static void AppendField(StringBuilder builder, string key, string value)
        {
            builder.Append('\n').Append(key);
            if (value == null)
            {
                builder.Append('!');
                return;
            }
            builder.Append('=').Append(value.Replace("\\", "\\\\").Replace("\n", "\\n"));
        }

        internal static string HashIdentity(string canonicalIdentity)
        {
            using (var sha = SHA256.Create())
            {
                var digest = sha.ComputeHash(Encoding.UTF8.GetBytes(canonicalIdentity));
                var builder = new StringBuilder(IdPrefix, IdPrefix.Length + 16);
                for (int i = 0; i < 8; i++)
                {
                    builder.Append(digest[i].ToString("x2", CultureInfo.InvariantCulture));
                }
                return builder.ToString();
            }
        }

        /// <summary>
        /// Hashes each canonical identity into an ID. Two entries with one ID - a hash collision or a
        /// genuinely duplicated identity - are both flagged and made non-applicable, never merged.
        /// </summary>
        private static void AssignIds(PrefabOverridesInspectResult result, List<PrefabOverrideInfo> overrides)
        {
            var byId = new Dictionary<string, PrefabOverrideInfo>(StringComparer.Ordinal);
            var collided = new List<PrefabOverrideInfo>();
            foreach (var entry in overrides)
            {
                entry.overrideId = HashIdentity(entry.CanonicalIdentity);
                if (!byId.TryGetValue(entry.overrideId, out var existing))
                {
                    byId[entry.overrideId] = entry;
                    continue;
                }

                if (!existing.idCollision)
                {
                    existing.idCollision = true;
                    collided.Add(existing);
                }
                entry.idCollision = true;
                collided.Add(entry);
                result.warnings.Add(string.Equals(existing.CanonicalIdentity, entry.CanonicalIdentity, StringComparison.Ordinal)
                    ? $"Override ID '{entry.overrideId}' is shared by two overrides with the same semantic identity; neither can be addressed safely."
                    : $"Override ID '{entry.overrideId}' collides between two different overrides; neither can be addressed safely.");
            }

            foreach (var entry in collided)
            {
                entry.applicable = false;
                entry.targetAssetPaths.Clear();
                entry.recommendedTargetAssetPath = null;
                entry.notApplicableReason =
                    $"Override ID '{entry.overrideId}' is not unique within this instance, so it cannot address this change safely.";
            }
        }

        private static int CompareOverrides(PrefabOverrideInfo a, PrefabOverrideInfo b)
        {
            int comparison = Array.IndexOf(CategoryOrder, a.category).CompareTo(Array.IndexOf(CategoryOrder, b.category));
            if (comparison != 0) return comparison;
            comparison = string.CompareOrdinal(a.objectPath ?? "", b.objectPath ?? "");
            if (comparison != 0) return comparison;
            comparison = string.CompareOrdinal(a.sourceObjectPath ?? "", b.sourceObjectPath ?? "");
            if (comparison != 0) return comparison;
            comparison = string.CompareOrdinal(a.ComponentTypeFullName ?? "", b.ComponentTypeFullName ?? "");
            if (comparison != 0) return comparison;
            comparison = a.ComponentOrdinalForIdentity.CompareTo(b.ComponentOrdinalForIdentity);
            if (comparison != 0) return comparison;
            comparison = string.CompareOrdinal(a.propertyPath ?? "", b.propertyPath ?? "");
            if (comparison != 0) return comparison;
            return string.CompareOrdinal(a.CanonicalIdentity, b.CanonicalIdentity);
        }

        private static void CountCategory(PrefabOverrideCounts counts, string category)
        {
            switch (category)
            {
                case CategoryModifiedProperty: counts.modifiedProperty++; break;
                case CategoryAddedComponent: counts.addedComponent++; break;
                case CategoryRemovedComponent: counts.removedComponent++; break;
                case CategoryAddedGameObject: counts.addedGameObject++; break;
                case CategoryRemovedGameObject: counts.removedGameObject++; break;
            }
        }

        private static PrefabPropertyValueInfo ReadValue(SerializedProperty property, string rawFallback)
        {
            var info = new PrefabPropertyValueInfo();
            switch (property.propertyType)
            {
                case SerializedPropertyType.Integer:
                    info.kind = "integer";
                    info.value = property.numericType == SerializedPropertyNumericType.UInt64
                        ? (object)property.ulongValue
                        : property.longValue;
                    break;
                case SerializedPropertyType.LayerMask:
                case SerializedPropertyType.ArraySize:
                    info.kind = property.propertyType == SerializedPropertyType.ArraySize ? "array_size" : "integer";
                    info.value = property.intValue;
                    break;
                case SerializedPropertyType.Boolean:
                    info.kind = "boolean";
                    info.value = property.boolValue;
                    break;
                case SerializedPropertyType.Float:
                    info.kind = "float";
                    info.value = FloatValue(property);
                    break;
                case SerializedPropertyType.String:
                    info.kind = "string";
                    info.value = property.stringValue;
                    break;
                case SerializedPropertyType.Character:
                    info.kind = "string";
                    info.value = ((char)property.intValue).ToString();
                    break;
                case SerializedPropertyType.Enum:
                    info.kind = "enum";
                    int index = property.enumValueIndex;
                    var names = property.enumNames;
                    info.value = index >= 0 && names != null && index < names.Length ? (object)names[index] : property.intValue;
                    break;
                case SerializedPropertyType.ObjectReference:
                    info.kind = "object_reference";
                    info.objectReference = DescribeReference(property.objectReferenceValue);
                    break;
                default:
                    info.kind = "other";
                    info.value = rawFallback;
                    break;
            }
            return info;
        }

        /// <summary>
        /// Floats are reported at their own round-trip precision (2.5, 0.1), not widened to a noisy
        /// double; non-finite values become strings because JSON has no NaN or Infinity.
        /// </summary>
        private static object FloatValue(SerializedProperty property)
        {
            double value = property.numericType == SerializedPropertyNumericType.Float
                ? double.Parse(property.floatValue.ToString("R", CultureInfo.InvariantCulture), CultureInfo.InvariantCulture)
                : property.doubleValue;
            if (double.IsNaN(value) || double.IsInfinity(value))
            {
                return value.ToString(CultureInfo.InvariantCulture);
            }
            return value;
        }

        /// <summary>Structured identity of a referenced object - never just its ToString().</summary>
        private static PrefabObjectReferenceInfo DescribeReference(UnityEngine.Object target)
        {
            if (target == null)
            {
                return new PrefabObjectReferenceInfo { isNull = true };
            }

            string typeName = "Object";
            string name = "";
            try
            {
                typeName = target.GetType().Name;
                name = target.name;
            }
            catch
            {
                // Broken or unreadable reference
            }

            var info = new PrefabObjectReferenceInfo { typeName = typeName, name = name };
            var transform = TransformOf(target);
            try
            {
                if (EditorUtility.IsPersistent(target))
                {
                    info.assetPath = AssetDatabase.GetAssetPath(target);
                    if (AssetDatabase.TryGetGUIDAndLocalFileIdentifier(target, out string guid, out long localFileId))
                    {
                        info.assetGuid = guid;
                        info.localFileId = localFileId;
                    }
                    if (transform != null)
                    {
                        info.hierarchyPath = HierarchyPaths.RelativePath(transform.root, transform);
                    }
                }
                else if (transform != null && transform.gameObject.scene.IsValid())
                {
                    info.scenePath = HierarchyPaths.SceneIdentity(transform.gameObject.scene);
                    info.hierarchyPath = HierarchyPaths.RootedPath(transform);
                }
            }
            catch
            {
                // Reference resolution failed safely
            }
            return info;
        }

        private static string Subject(PrefabOverrideInfo entry)
        {
            string subject = DisplayPath(entry.objectPath);
            if (entry.componentType == null) return subject;
            string ordinal = entry.componentOrdinal.HasValue
                ? "[" + entry.componentOrdinal.Value.ToString(CultureInfo.InvariantCulture) + "]"
                : "";
            return subject + " " + entry.componentType + ordinal;
        }

        private static string DisplayPath(string path)
        {
            if (path == null) return "an unknown object";
            return path.Length == 0 ? "the instance root" : "'" + path + "'";
        }

        private static string ValueText(PrefabPropertyValueInfo value)
        {
            if (value == null) return "(absent in source)";
            if (value.kind == "object_reference")
            {
                var reference = value.objectReference;
                return reference == null || reference.isNull ? "None" : $"'{reference.name}' ({reference.typeName})";
            }
            switch (value.value)
            {
                case null: return "(unreadable)";
                case bool boolean: return boolean ? "true" : "false";
                case string text: return "'" + text + "'";
                case IFormattable formattable: return formattable.ToString(null, CultureInfo.InvariantCulture);
                default: return value.value.ToString();
            }
        }

        private static Transform TransformOf(UnityEngine.Object value)
        {
            if (value == null) return null;
            try
            {
                if (value is GameObject gameObject) return gameObject != null ? gameObject.transform : null;
                if (value is Component component) return component != null ? component.transform : null;
            }
            catch
            {
                return null;
            }
            return null;
        }

        private static GameObject GameObjectOf(UnityEngine.Object value)
        {
            if (value == null) return null;
            try
            {
                if (value is GameObject gameObject) return gameObject;
                if (value is Component component) return component != null ? component.gameObject : null;
            }
            catch
            {
                return null;
            }
            return null;
        }

        private sealed class InspectionContext
        {
            public readonly PrefabOverridesInspectResult Result;
            public readonly GameObject Root;
            public readonly SerializedObjectCache Readers;

            /// <summary>
            /// Roots whose override lists are read: the scope root and, for a nested scope, the
            /// outermost root that actually stores the scene's modifications. Results are
            /// de-duplicated and filtered to the scope root's subtree.
            /// </summary>
            public readonly List<GameObject> OverrideHandles = new List<GameObject>();

            private readonly Dictionary<string, bool> editable = new Dictionary<string, bool>(StringComparer.Ordinal);

            public InspectionContext(PrefabOverridesInspectResult result, GameObject root, GameObject outermostRoot, SerializedObjectCache readers)
            {
                Result = result;
                Root = root;
                Readers = readers;
                OverrideHandles.Add(root);
                if (outermostRoot != root)
                {
                    OverrideHandles.Add(outermostRoot);
                }
            }

            public bool InScope(Transform transform)
            {
                return transform != null && transform.IsChildOf(Root.transform);
            }

            public bool IsEditable(string assetPath)
            {
                if (!editable.TryGetValue(assetPath, out bool value))
                {
                    value = PrefabInspectionService.IsEditablePrefabAsset(assetPath);
                    editable[assetPath] = value;
                }
                return value;
            }
        }

        /// <summary>One read-only SerializedObject per inspected object, all disposed together.</summary>
        private sealed class SerializedObjectCache : IDisposable
        {
            private readonly Dictionary<UnityEngine.Object, SerializedObject> readers =
                new Dictionary<UnityEngine.Object, SerializedObject>();

            public SerializedObject Get(UnityEngine.Object target)
            {
                if (!readers.TryGetValue(target, out var reader))
                {
                    reader = new SerializedObject(target);
                    readers[target] = reader;
                }
                return reader;
            }

            public void Dispose()
            {
                foreach (var reader in readers.Values)
                {
                    reader.Dispose();
                }
                readers.Clear();
            }
        }
    }
}
