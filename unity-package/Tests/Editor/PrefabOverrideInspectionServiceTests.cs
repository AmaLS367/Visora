using System;
using System.Collections.Generic;
using System.Globalization;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    /// <summary>
    /// EditMode coverage for the read-only Prefab instance override diff. Every fixture builds real
    /// Prefab assets and scene instances, mutates the instance the way a user would, and inspects
    /// it through the same entry point the HTTP endpoint uses.
    /// </summary>
    public class PrefabOverrideInspectionServiceTests
    {
        private const string TestFolderName = "VisoraPrefabOverrideTests";
        private const string TestFolder = "Assets/" + TestFolderName;
        private const int Limit = 200;
        private const string IdPattern = "^ovr_[0-9a-f]{16}$";

        [SetUp]
        public void SetUp()
        {
            if (!AssetDatabase.IsValidFolder(TestFolder))
            {
                AssetDatabase.CreateFolder("Assets", TestFolderName);
            }
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            AssetDatabase.DeleteAsset(TestFolder);
            AssetDatabase.Refresh();
            LogAssert.ignoreFailingMessages = false;
        }

        // ------------------------------------------------------------------------------------
        // Fixture helpers
        // ------------------------------------------------------------------------------------

        private static GameObject Child(GameObject parent, string name)
        {
            var child = new GameObject(name);
            child.transform.SetParent(parent.transform, false);
            return child;
        }

        private static string SavePrefab(GameObject root, string name)
        {
            string path = $"{TestFolder}/{name}.prefab";
            PrefabUtility.SaveAsPrefabAsset(root, path);
            UnityEngine.Object.DestroyImmediate(root);
            AssetDatabase.Refresh();
            return path;
        }

        /// <summary>
        /// Root with two BoxColliders; 'Lid' (BoxCollider), 'Body' (MeshFilter + MeshRenderer), two
        /// same-name 'Arm' children, and 'Handle'.
        /// </summary>
        private static string CreateCratePrefab(string name)
        {
            var root = new GameObject(name);
            root.AddComponent<BoxCollider>();
            root.AddComponent<BoxCollider>();
            Child(root, "Lid").AddComponent<BoxCollider>();
            var body = Child(root, "Body");
            body.AddComponent<MeshFilter>();
            body.AddComponent<MeshRenderer>();
            Child(root, "Arm");
            Child(root, "Arm");
            Child(root, "Handle");
            return SavePrefab(root, name);
        }

        private static string CreateModelAsset(string name)
        {
            string path = $"{TestFolder}/{name}.obj";
            System.IO.File.WriteAllText(path, "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n");
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            AssetDatabase.Refresh();
            return path;
        }

        private static GameObject Spawn(string assetPath)
        {
            return (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(assetPath));
        }

        private static void SetFloat(UnityEngine.Object target, string propertyPath, float value)
        {
            using (var serialized = new SerializedObject(target))
            {
                var property = serialized.FindProperty(propertyPath);
                Assert.That(property, Is.Not.Null, propertyPath);
                property.floatValue = value;
                serialized.ApplyModifiedPropertiesWithoutUndo();
            }
        }

        private static void SetReference(UnityEngine.Object target, string propertyPath, UnityEngine.Object value)
        {
            using (var serialized = new SerializedObject(target))
            {
                var property = serialized.FindProperty(propertyPath);
                Assert.That(property, Is.Not.Null, propertyPath);
                property.objectReferenceValue = value;
                serialized.ApplyModifiedPropertiesWithoutUndo();
            }
        }

        private static PrefabOverridesInspectResult Inspect(
            string path,
            bool includeDefaults = false,
            string scope = "nearest",
            int maxOverrides = Limit,
            string scenePath = null)
        {
            return PrefabOverrideInspectionService.InspectPrefabOverrides(path, scenePath, includeDefaults, scope, maxOverrides);
        }

        private static string Describe(PrefabOverridesInspectResult result)
        {
            return (result.error ?? "") + " | " + string.Join("; ", result.overrides.ConvertAll(o =>
                o.category + ":" + o.objectPath + ":" + o.componentType + ":" + o.propertyPath));
        }

        private static PrefabOverrideInfo Single(
            PrefabOverridesInspectResult result,
            string category,
            string objectPath,
            string propertyPath = null,
            string componentType = null)
        {
            var matches = result.overrides.FindAll(o =>
                o.category == category &&
                o.objectPath == objectPath &&
                (propertyPath == null || o.propertyPath == propertyPath) &&
                (componentType == null || o.componentType == componentType));
            Assert.That(matches.Count, Is.EqualTo(1), Describe(result));
            return matches[0];
        }

        private static double Number(PrefabPropertyValueInfo value)
        {
            Assert.That(value, Is.Not.Null);
            return Convert.ToDouble(value.value, CultureInfo.InvariantCulture);
        }

        private static void AssertWellFormedIds(PrefabOverridesInspectResult result)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var entry in result.overrides)
            {
                Assert.That(entry.overrideId, Does.Match(IdPattern));
                Assert.That(seen.Add(entry.overrideId), Is.True, $"Duplicate override ID {entry.overrideId}");
                Assert.That(entry.idCollision, Is.False);
                Assert.That(entry.description, Is.Not.Empty);
            }
            Assert.That(result.overrideCounts.modifiedProperty + result.overrideCounts.addedComponent +
                        result.overrideCounts.removedComponent + result.overrideCounts.addedGameObject +
                        result.overrideCounts.removedGameObject, Is.EqualTo(result.totalOverrideCount));
        }

        // ------------------------------------------------------------------------------------
        // Categories
        // ------------------------------------------------------------------------------------

        [Test]
        public void ReportsNoOverridesForAFreshInstance()
        {
            string path = CreateCratePrefab("Crate");
            Spawn(path);

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.totalOverrideCount, Is.EqualTo(0), Describe(result));
            Assert.That(result.overrides, Is.Empty);
            Assert.That(result.truncated, Is.False);
            Assert.That(result.connectionStatus, Is.EqualTo("connected"));
            Assert.That(result.prefabKind, Is.EqualTo("regular"));
            Assert.That(result.sourceAssetPath, Is.EqualTo(path));
            Assert.That(result.sourceGuid, Is.EqualTo(AssetDatabase.AssetPathToGUID(path)));
            Assert.That(result.instanceRootPath, Is.EqualTo("Crate"));
            Assert.That(result.outermostInstanceRootPath, Is.EqualTo("Crate"));
            Assert.That(result.scope, Is.EqualTo("nearest"));
        }

        [Test]
        public void ReportsAModifiedSerializedPropertyWithSourceAndInstanceValues()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            SetFloat(instance.transform.Find("Lid").GetComponent<BoxCollider>(), "m_Size.x", 3f);

            var result = Inspect("Crate/Lid");

            Assert.That(result.success, Is.True, result.error);
            var entry = Single(result, "modified_property", "Lid", "m_Size.x");
            Assert.That(entry.sourceObjectPath, Is.EqualTo("Lid"));
            Assert.That(entry.componentType, Is.EqualTo("BoxCollider"));
            Assert.That(entry.componentOrdinal, Is.Null);
            Assert.That(entry.sourceValue.kind, Is.EqualTo("float"));
            Assert.That(Number(entry.sourceValue), Is.EqualTo(1.0));
            Assert.That(Number(entry.instanceValue), Is.EqualTo(3.0));
            Assert.That(entry.isDefaultOverride, Is.False);
            Assert.That(entry.applicable, Is.True, entry.notApplicableReason);
            Assert.That(entry.targetAssetPaths, Is.EqualTo(new List<string> { path }));
            Assert.That(entry.recommendedTargetAssetPath, Is.EqualTo(path));
            Assert.That(result.overrideCounts.modifiedProperty, Is.GreaterThanOrEqualTo(1));
            AssertWellFormedIds(result);
        }

        [Test]
        public void ReportsObjectReferenceOverridesWithStructuredIdentity()
        {
            string meshPath = $"{TestFolder}/Dented.asset";
            AssetDatabase.CreateAsset(new Mesh { name = "Dented" }, meshPath);
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            var mesh = AssetDatabase.LoadAssetAtPath<Mesh>(meshPath);
            SetReference(instance.transform.Find("Body").GetComponent<MeshFilter>(), "m_Mesh", mesh);

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            var entry = Single(result, "modified_property", "Body", "m_Mesh");
            Assert.That(entry.componentType, Is.EqualTo("MeshFilter"));
            Assert.That(entry.sourceValue.kind, Is.EqualTo("object_reference"));
            Assert.That(entry.sourceValue.objectReference.isNull, Is.True);
            var reference = entry.instanceValue.objectReference;
            Assert.That(entry.instanceValue.kind, Is.EqualTo("object_reference"));
            Assert.That(reference.isNull, Is.False);
            Assert.That(reference.typeName, Is.EqualTo("Mesh"));
            Assert.That(reference.name, Is.EqualTo("Dented"));
            Assert.That(reference.assetPath, Is.EqualTo(meshPath));
            Assert.That(reference.assetGuid, Is.EqualTo(AssetDatabase.AssetPathToGUID(meshPath)));
            Assert.That(reference.localFileId.HasValue, Is.True);
            Assert.That(entry.applicable, Is.True, entry.notApplicableReason);
        }

        [Test]
        public void ExcludesDefaultRootTransformOverridesUnlessRequestedAndNeverAppliesThem()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            SetFloat(instance.transform, "m_LocalPosition.x", 5f);

            var filtered = Inspect("Crate");
            var included = Inspect("Crate", includeDefaults: true);

            Assert.That(filtered.success, Is.True, filtered.error);
            Assert.That(filtered.overrides.Exists(o => o.propertyPath == "m_LocalPosition.x"), Is.False, Describe(filtered));
            Assert.That(filtered.excludedDefaultOverrideCount, Is.GreaterThanOrEqualTo(1));
            Assert.That(filtered.includeDefaultOverrides, Is.False);

            Assert.That(included.success, Is.True, included.error);
            var entry = Single(included, "modified_property", "", "m_LocalPosition.x");
            Assert.That(entry.isDefaultOverride, Is.True);
            Assert.That(entry.applicable, Is.False);
            Assert.That(entry.notApplicableReason, Does.Contain("default override"));
            Assert.That(entry.targetAssetPaths, Is.Empty);
            Assert.That(entry.recommendedTargetAssetPath, Is.Null);
            Assert.That(Number(entry.instanceValue), Is.EqualTo(5.0));
            Assert.That(included.excludedDefaultOverrideCount, Is.EqualTo(0));
            Assert.That(included.totalOverrideCount, Is.EqualTo(filtered.totalOverrideCount + filtered.excludedDefaultOverrideCount));
        }

        [Test]
        public void ReportsAnAddedComponent()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            instance.transform.Find("Lid").gameObject.AddComponent<SphereCollider>();

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            var entry = Single(result, "added_component", "Lid");
            Assert.That(entry.componentType, Is.EqualTo("SphereCollider"));
            Assert.That(entry.sourceObjectPath, Is.EqualTo("Lid"));
            Assert.That(entry.applicable, Is.True, entry.notApplicableReason);
            Assert.That(entry.targetAssetPaths, Is.EqualTo(new List<string> { path }));
            Assert.That(result.overrideCounts.addedComponent, Is.EqualTo(1));
        }

        [Test]
        public void ReportsARemovedComponent()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            UnityEngine.Object.DestroyImmediate(instance.transform.Find("Body").GetComponent<MeshRenderer>());

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            var entry = Single(result, "removed_component", "Body");
            Assert.That(entry.componentType, Is.EqualTo("MeshRenderer"));
            Assert.That(entry.sourceObjectPath, Is.EqualTo("Body"));
            Assert.That(entry.applicable, Is.True, entry.notApplicableReason);
            Assert.That(entry.targetAssetPaths, Is.EqualTo(new List<string> { path }));
            Assert.That(result.overrideCounts.removedComponent, Is.EqualTo(1));
        }

        [Test]
        public void ReportsAnAddedChildGameObject()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            Child(instance, "Extra");

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            var entry = Single(result, "added_game_object", "Extra");
            Assert.That(entry.sourceObjectPath, Is.Null);
            Assert.That(entry.applicable, Is.True, entry.notApplicableReason);
            Assert.That(entry.targetAssetPaths, Is.EqualTo(new List<string> { path }));
            Assert.That(result.overrideCounts.addedGameObject, Is.EqualTo(1));
        }

        [Test]
        public void AcceptsAPathToAnAddedGameObjectAndInspectsItsContainingInstance()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            Child(instance, "Extra");

            var result = Inspect("Crate/Extra");

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.instanceRootPath, Is.EqualTo("Crate"));
            Assert.That(result.warnings.Exists(w => w.Contains("added GameObject")), Is.True);
        }

        [Test]
        public void ReportsARemovedChildGameObject()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            UnityEngine.Object.DestroyImmediate(instance.transform.Find("Handle").gameObject);

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            var entry = Single(result, "removed_game_object", "");
            Assert.That(entry.sourceObjectPath, Is.EqualTo("Handle"));
            Assert.That(entry.applicable, Is.True, entry.notApplicableReason);
            Assert.That(entry.targetAssetPaths, Is.EqualTo(new List<string> { path }));
            Assert.That(result.overrideCounts.removedGameObject, Is.EqualTo(1));
        }

        // ------------------------------------------------------------------------------------
        // Nested, Variant, Model
        // ------------------------------------------------------------------------------------

        [Test]
        public void DistinguishesNearestAndOutermostScopesForNestedPrefabs()
        {
            var bladeRoot = new GameObject("Blade");
            Child(bladeRoot, "Edge").AddComponent<BoxCollider>();
            string innerPath = SavePrefab(bladeRoot, "Blade");

            var swordRoot = new GameObject("Sword");
            var nested = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(innerPath));
            nested.transform.SetParent(swordRoot.transform, false);
            string outerPath = SavePrefab(swordRoot, "Sword");

            var instance = Spawn(outerPath);
            SetFloat(instance.transform.Find("Blade/Edge").GetComponent<BoxCollider>(), "m_Size.x", 4f);

            var nearest = Inspect("Sword/Blade/Edge");
            var outermost = Inspect("Sword/Blade/Edge", scope: "outermost");

            Assert.That(nearest.success, Is.True, nearest.error);
            Assert.That(nearest.instanceRootPath, Is.EqualTo("Sword/Blade"));
            Assert.That(nearest.outermostInstanceRootPath, Is.EqualTo("Sword"));
            Assert.That(nearest.sourceAssetPath, Is.EqualTo(innerPath));
            var nearestEntry = Single(nearest, "modified_property", "Edge", "m_Size.x");
            Assert.That(nearestEntry.sourceObjectPath, Is.EqualTo("Edge"));
            Assert.That(nearestEntry.targetAssetPaths, Is.EqualTo(new List<string> { outerPath, innerPath }),
                "Targets run from the immediate (outer) source inwards to the asset that introduced the object.");
            Assert.That(nearestEntry.recommendedTargetAssetPath, Is.EqualTo(innerPath),
                "The outermost Prefab must not be assumed to be the right target.");

            Assert.That(outermost.success, Is.True, outermost.error);
            Assert.That(outermost.instanceRootPath, Is.EqualTo("Sword"));
            Assert.That(outermost.sourceAssetPath, Is.EqualTo(outerPath));
            var outerEntry = Single(outermost, "modified_property", "Blade/Edge", "m_Size.x");
            Assert.That(outerEntry.sourceObjectPath, Is.EqualTo("Blade/Edge"));
            Assert.That(outerEntry.targetAssetPaths, Is.EqualTo(new List<string> { outerPath, innerPath }));
            Assert.That(outerEntry.recommendedTargetAssetPath, Is.EqualTo(outerPath));

            Assert.That(outerEntry.overrideId, Is.Not.EqualTo(nearestEntry.overrideId),
                "The scope is part of an override's target context.");
        }

        [Test]
        public void ReportsVariantInstancesWithTheVariantAndItsBaseAsTargets()
        {
            string basePath = CreateCratePrefab("CrateBase");
            var authoring = Spawn(basePath);
            string variantPath = $"{TestFolder}/CrateVariant.prefab";
            PrefabUtility.SaveAsPrefabAsset(authoring, variantPath);
            UnityEngine.Object.DestroyImmediate(authoring);
            AssetDatabase.Refresh();

            var instance = Spawn(variantPath);
            SetFloat(instance.transform.Find("Lid").GetComponent<BoxCollider>(), "m_Size.z", 2f);

            var result = Inspect(instance.name + "/Lid");

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.prefabKind, Is.EqualTo("variant"));
            Assert.That(result.sourceAssetPath, Is.EqualTo(variantPath));
            var entry = Single(result, "modified_property", "Lid", "m_Size.z");
            Assert.That(entry.targetAssetPaths, Is.EqualTo(new List<string> { variantPath, basePath }));
            Assert.That(entry.recommendedTargetAssetPath, Is.EqualTo(variantPath));
        }

        [Test]
        public void MarksModelPrefabOverridesAsNonApplicable()
        {
            string modelPath = CreateModelAsset("TestModel");
            var instance = Spawn(modelPath);
            SetFloat(instance.transform, "m_LocalScale.x", 2f);

            var result = Inspect(instance.name);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.prefabKind, Is.EqualTo("model"));
            Assert.That(result.sourceAssetPath, Is.EqualTo(modelPath));
            Assert.That(result.warnings.Exists(w => w.Contains("Model Prefab")), Is.True);
            var entry = Single(result, "modified_property", "", "m_LocalScale.x");
            Assert.That(entry.isDefaultOverride, Is.False);
            Assert.That(entry.applicable, Is.False);
            Assert.That(entry.notApplicableReason, Does.Contain("Model Prefab"));
            Assert.That(entry.targetAssetPaths, Is.Empty);
        }

        // ------------------------------------------------------------------------------------
        // Identity: ordinals, sibling names, IDs
        // ------------------------------------------------------------------------------------

        [Test]
        public void DistinguishesSeveralComponentsOfTheSameTypeByOrdinal()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            var colliders = instance.GetComponents<BoxCollider>();
            SetFloat(colliders[0], "m_Size.y", 2f);
            SetFloat(colliders[1], "m_Size.y", 3f);

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            var matches = result.overrides.FindAll(o => o.propertyPath == "m_Size.y" && o.objectPath == "");
            Assert.That(matches.Count, Is.EqualTo(2), Describe(result));
            Assert.That(matches[0].componentOrdinal, Is.EqualTo(0));
            Assert.That(matches[1].componentOrdinal, Is.EqualTo(1));
            Assert.That(Number(matches[0].instanceValue), Is.EqualTo(2.0));
            Assert.That(Number(matches[1].instanceValue), Is.EqualTo(3.0));
            Assert.That(matches[0].overrideId, Is.Not.EqualTo(matches[1].overrideId));
            AssertWellFormedIds(result);
        }

        [Test]
        public void AddressesSameNameSiblingsWithIndexedPathsAndReportsAmbiguity()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            instance.transform.GetChild(3).gameObject.AddComponent<SphereCollider>(); // the second 'Arm'

            var indexed = Inspect("Crate/Arm[1]");
            var ambiguous = Inspect("Crate/Arm");

            Assert.That(indexed.success, Is.True, indexed.error);
            var entry = Single(indexed, "added_component", "Arm[1]");
            Assert.That(entry.sourceObjectPath, Is.EqualTo("Arm[1]"));

            Assert.That(ambiguous.success, Is.False);
            Assert.That(ambiguous.error, Does.Contain("ambiguous"));
            Assert.That(ambiguous.overrides, Is.Empty);
            Assert.That(ambiguous.pathCandidates.ConvertAll(c => c.hierarchyPath),
                Is.EqualTo(new List<string> { "Crate/Arm[0]", "Crate/Arm[1]" }));
        }

        [Test]
        public void HashesCanonicalIdentitiesWithSha256()
        {
            // SHA-256("abc") starts with ba7816bf8f01cfea.
            Assert.That(PrefabOverrideInspectionService.HashIdentity("abc"), Is.EqualTo("ovr_ba7816bf8f01cfea"));
        }

        [Test]
        public void TruncatesDeterministicallyAndKeepsRealTotals()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            SetFloat(instance.transform.Find("Lid").GetComponent<BoxCollider>(), "m_Size.x", 3f);
            instance.transform.Find("Lid").gameObject.AddComponent<SphereCollider>();
            Child(instance, "Extra");

            var full = Inspect("Crate");
            var capped = Inspect("Crate", maxOverrides: 1);

            Assert.That(capped.success, Is.True, capped.error);
            Assert.That(capped.truncated, Is.True);
            Assert.That(capped.overrides.Count, Is.EqualTo(1));
            Assert.That(capped.totalOverrideCount, Is.EqualTo(full.totalOverrideCount));
            Assert.That(capped.overrides[0].overrideId, Is.EqualTo(full.overrides[0].overrideId));
            Assert.That(capped.warnings.Exists(w => w.Contains("max_overrides")), Is.True);
        }

        // ------------------------------------------------------------------------------------
        // Path resolution and broken states
        // ------------------------------------------------------------------------------------

        [Test]
        public void ReportsMissingHierarchyPathsWithTheDeepestExistingPrefix()
        {
            string path = CreateCratePrefab("Crate");
            Spawn(path);

            var missingRoot = Inspect("Nope/Nothing");
            var missingChild = Inspect("Crate/Nope");

            Assert.That(missingRoot.success, Is.False);
            Assert.That(missingRoot.error, Does.Contain("No GameObject"));
            Assert.That(missingChild.success, Is.False);
            Assert.That(missingChild.error, Does.Contain("deepest existing prefix is 'Crate'"));
        }

        [Test]
        public void RejectsObjectsThatAreNotPartOfAPrefabInstance()
        {
            new GameObject("Plain");

            var result = Inspect("Plain");

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("not part of a Prefab instance"));
        }

        [Test]
        public void RejectsAnUnknownScope()
        {
            var result = Inspect("Crate", scope: "innermost");

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("Unknown scope"));
        }

        [Test]
        public void ResolvesInstancesAcrossLoadedScenesAndReportsCrossSceneAmbiguity()
        {
            string path = CreateCratePrefab("Crate");
            Spawn(path);
            // Only one untitled scene may be loaded at a time, so the first one is saved.
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene(), $"{TestFolder}/First.unity");
            var second = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(path), second);
            string secondPath = $"{TestFolder}/Second.unity";
            EditorSceneManager.SaveScene(second, secondPath);

            var ambiguous = Inspect("Crate");
            var scoped = Inspect("Crate", scenePath: secondPath);
            var unknownScene = Inspect("Crate", scenePath: "Assets/NotLoaded.unity");

            Assert.That(ambiguous.success, Is.False);
            Assert.That(ambiguous.error, Does.Contain("ambiguous"));
            Assert.That(ambiguous.pathCandidates.Count, Is.EqualTo(2));
            Assert.That(ambiguous.pathCandidates.Exists(c => c.scenePath == secondPath), Is.True);

            Assert.That(scoped.success, Is.True, scoped.error);
            Assert.That(scoped.scenePath, Is.EqualTo(secondPath));
            Assert.That(scoped.instanceRootPath, Is.EqualTo("Crate"));

            Assert.That(unknownScene.success, Is.False);
            Assert.That(unknownScene.error, Does.Contain("is not loaded"));
        }

        [Test]
        public void ReportsAMissingSourceAssetAsAFailedInspection()
        {
            string path = CreateCratePrefab("Doomed");
            Spawn(path);

            LogAssert.ignoreFailingMessages = true;
            AssetDatabase.DeleteAsset(path);
            AssetDatabase.Refresh();

            var result = Inspect("Doomed");

            Assert.That(result.success, Is.False);
            Assert.That(result.connectionStatus, Is.EqualTo("missing_asset"), result.error);
            Assert.That(result.error, Does.Contain("missing"));
            Assert.That(result.overrides, Is.Empty);
        }

        // ------------------------------------------------------------------------------------
        // Safety and determinism
        // ------------------------------------------------------------------------------------

        [Test]
        public void IsReadOnlyAndDeterministicAcrossRepeatedCalls()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            var lid = instance.transform.Find("Lid").gameObject;
            var lidCollider = lid.GetComponent<BoxCollider>();
            SetFloat(lidCollider, "m_Size.x", 3f);
            lid.AddComponent<SphereCollider>();
            Child(instance, "Extra");
            UnityEngine.Object.DestroyImmediate(instance.transform.Find("Body").GetComponent<MeshRenderer>());

            Selection.activeGameObject = lid;
            var scene = SceneManager.GetActiveScene();
            bool wasDirty = scene.isDirty;
            int rootCount = scene.rootCount;
            int sceneCount = SceneManager.sceneCount;
            int transformCount = instance.GetComponentsInChildren<Transform>(true).Length;
            int instanceDirtyCount = EditorUtility.GetDirtyCount(instance);
            int colliderDirtyCount = EditorUtility.GetDirtyCount(lidCollider);
            int undoGroup = Undo.GetCurrentGroup();
            var selectionBefore = Selection.objects;

            var first = Inspect("Crate/Lid", includeDefaults: true);
            var second = Inspect("Crate/Lid", includeDefaults: true);

            Assert.That(first.success, Is.True, first.error);
            Assert.That(first.totalOverrideCount, Is.GreaterThanOrEqualTo(4), Describe(first));
            AssertWellFormedIds(first);
            Assert.That(second.overrides.ConvertAll(o => o.overrideId), Is.EqualTo(first.overrides.ConvertAll(o => o.overrideId)),
                "Identical scene state must produce identical override IDs in identical order.");
            Assert.That(second.overrides.ConvertAll(o => o.description), Is.EqualTo(first.overrides.ConvertAll(o => o.description)));
            Assert.That(VisoraJson.Serialize(second), Is.EqualTo(VisoraJson.Serialize(first)));

            Assert.That(SceneManager.GetActiveScene().path, Is.EqualTo(scene.path), "Active scene must not change.");
            Assert.That(scene.isDirty, Is.EqualTo(wasDirty), "Scene dirty state must not change.");
            Assert.That(scene.rootCount, Is.EqualTo(rootCount), "No scene objects may be created.");
            Assert.That(SceneManager.sceneCount, Is.EqualTo(sceneCount), "No scene may be opened or closed.");
            Assert.That(instance.GetComponentsInChildren<Transform>(true).Length, Is.EqualTo(transformCount));
            Assert.That(EditorUtility.GetDirtyCount(instance), Is.EqualTo(instanceDirtyCount));
            Assert.That(EditorUtility.GetDirtyCount(lidCollider), Is.EqualTo(colliderDirtyCount));
            Assert.That(Undo.GetCurrentGroup(), Is.EqualTo(undoGroup), "Inspection must not record Undo.");
            Assert.That(Selection.activeGameObject, Is.SameAs(lid), "Selection must not change.");
            Assert.That(Selection.objects, Is.EqualTo(selectionBefore));
            Assert.That(PrefabStageUtility.GetCurrentPrefabStage(), Is.Null, "No Prefab Stage may be opened.");
            Assert.That(lidCollider.size.x, Is.EqualTo(3f), "Overrides must not be reverted.");
            Assert.That(AssetDatabase.LoadAssetAtPath<GameObject>(path).transform.Find("Lid").GetComponent<BoxCollider>().size.x,
                Is.EqualTo(1f), "Overrides must not be applied to the asset.");
        }

        [Test]
        public void ResolvesScenePathWithLeadingSlashAndWindowsSeparators()
        {
            string path = CreateCratePrefab("Crate");
            Spawn(path);
            EditorSceneManager.SaveScene(SceneManager.GetActiveScene(), $"{TestFolder}/First.unity");
            var second = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(path), second);
            string secondPath = $"{TestFolder}/Second.unity";
            EditorSceneManager.SaveScene(second, secondPath);

            string leadingSlashPath = "/" + secondPath.Replace("/", "\\");
            var result = Inspect("Crate", scenePath: leadingSlashPath);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.scenePath, Is.EqualTo(secondPath));
            Assert.That(result.instanceRootPath, Is.EqualTo("Crate"));
        }

        [Test]
        public void DistinguishesAddedGameObjectsSharingNameWithIndexedPaths()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            var lid = instance.transform.Find("Lid").gameObject;
            Child(lid, "Decal");
            Child(lid, "Decal");

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.overrideCounts.addedGameObject, Is.EqualTo(2));
            var decal0 = Single(result, "added_game_object", "Lid/Decal[0]");
            var decal1 = Single(result, "added_game_object", "Lid/Decal[1]");
            Assert.That(decal0.overrideId, Does.Match(IdPattern));
            Assert.That(decal1.overrideId, Does.Match(IdPattern));
            Assert.That(decal0.overrideId, Is.Not.EqualTo(decal1.overrideId));
            AssertWellFormedIds(result);
        }

        [Test]
        public void DistinguishesMultipleAddedComponentsOfTheSameTypeByOrdinal()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            var lid = instance.transform.Find("Lid").gameObject;
            lid.AddComponent<SphereCollider>();
            lid.AddComponent<SphereCollider>();

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.overrideCounts.addedComponent, Is.EqualTo(2));
            var added = result.overrides.FindAll(o => o.category == "added_component" && o.componentType == "SphereCollider");
            Assert.That(added.Count, Is.EqualTo(2));
            Assert.That(added[0].componentOrdinal, Is.EqualTo(0));
            Assert.That(added[1].componentOrdinal, Is.EqualTo(1));
            Assert.That(added[0].overrideId, Is.Not.EqualTo(added[1].overrideId));
            AssertWellFormedIds(result);
        }

        [Test]
        public void SafelyHandlesBrokenReferencesWithoutThrowing()
        {
            string path = CreateCratePrefab("Crate");
            var instance = Spawn(path);
            var tempMesh = new Mesh { name = "TempMesh" };
            var meshFilter = instance.transform.Find("Body").GetComponent<MeshFilter>();
            SetReference(meshFilter, "m_Mesh", tempMesh);
            UnityEngine.Object.DestroyImmediate(tempMesh);

            var result = Inspect("Crate");

            Assert.That(result.success, Is.True, result.error);
            var entry = Single(result, "modified_property", "Body", "m_Mesh");
            Assert.That(entry.instanceValue.kind, Is.EqualTo("object_reference"));
            Assert.That(entry.instanceValue.objectReference.isNull, Is.True);
            AssertWellFormedIds(result);
        }
    }
}
