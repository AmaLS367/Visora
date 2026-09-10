using System;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    /// <summary>
    /// EditMode coverage for read-only Prefab asset inspection. Every test asserts the user's active
    /// scene is left exactly as it was, because the whole point of this tool is inspecting a Prefab
    /// without instantiating it anywhere the user can see.
    /// </summary>
    public class PrefabInspectionServiceTests
    {
        private const string TestFolderName = "VisoraPrefabInspectionTests";
        private const string TestFolder = "Assets/" + TestFolderName;
        private const int Limit = 200;

        private string activeScenePath;
        private string activeSceneName;
        private bool activeSceneWasDirty;
        private int activeSceneRootCount;
        private int loadedSceneCount;

        [SetUp]
        public void SetUp()
        {
            if (!AssetDatabase.IsValidFolder(TestFolder))
            {
                AssetDatabase.CreateFolder("Assets", TestFolderName);
            }

            var scene = SceneManager.GetActiveScene();
            activeScenePath = scene.path;
            activeSceneName = scene.name;
            activeSceneWasDirty = scene.isDirty;
            activeSceneRootCount = scene.rootCount;
            loadedSceneCount = SceneManager.sceneCount;
        }

        [TearDown]
        public void TearDown()
        {
            AssetDatabase.DeleteAsset(TestFolder);
            AssetDatabase.Refresh();
            // Reset last: tearing down a deliberately broken Prefab fixture makes Unity log its own
            // import errors, which must not be attributed to the next test.
            LogAssert.ignoreFailingMessages = false;
        }

        /// <summary>
        /// The invariant every inspection must hold: no stage opened, no scene added or switched,
        /// no object left behind in the user's scene, and the dirty flag untouched.
        /// </summary>
        private void AssertEditorStatePreserved()
        {
            var scene = SceneManager.GetActiveScene();
            Assert.That(UnityEditor.SceneManagement.PrefabStageUtility.GetCurrentPrefabStage(), Is.Null,
                "Inspection must not open a Prefab Stage.");
            Assert.That(scene.path, Is.EqualTo(activeScenePath), "Active scene must not change.");
            Assert.That(scene.name, Is.EqualTo(activeSceneName), "Active scene must not change.");
            Assert.That(scene.isDirty, Is.EqualTo(activeSceneWasDirty), "Active scene dirty state must not change.");
            Assert.That(scene.rootCount, Is.EqualTo(activeSceneRootCount),
                "Inspection must not add objects to the active scene.");
            Assert.That(SceneManager.sceneCount, Is.EqualTo(loadedSceneCount), "No scene may be opened or closed.");
        }

        private static string CreateRegularPrefab(string name)
        {
            var root = new GameObject(name);
            root.AddComponent<BoxCollider>();

            var child = new GameObject("Child");
            child.transform.SetParent(root.transform, false);
            child.AddComponent<MeshFilter>();
            child.SetActive(false);

            var grandChild = new GameObject("GrandChild");
            grandChild.transform.SetParent(child.transform, false);

            string path = $"{TestFolder}/{name}.prefab";
            PrefabUtility.SaveAsPrefabAsset(root, path);
            UnityEngine.Object.DestroyImmediate(root);
            AssetDatabase.Refresh();
            return path;
        }

        [Test]
        public void InspectsRegularPrefabHierarchyDeterministically()
        {
            string path = CreateRegularPrefab("Regular");

            var first = PrefabInspectionService.InspectPrefabAsset(path, Limit);
            var second = PrefabInspectionService.InspectPrefabAsset(path, Limit);

            Assert.That(first.success, Is.True, first.error);
            Assert.That(first.prefabKind, Is.EqualTo("regular"));
            Assert.That(first.prefabName, Is.EqualTo("Regular"));
            Assert.That(first.assetGuid, Is.Not.Empty);
            Assert.That(first.basePrefabPath, Is.Null);
            Assert.That(first.rootConnectionStatus, Is.EqualTo("not_an_instance"));
            Assert.That(first.rootObjectName, Is.EqualTo("Regular"));
            Assert.That(first.totalObjectCount, Is.EqualTo(3));
            Assert.That(first.truncated, Is.False);
            Assert.That(first.editTargetAssetPaths, Is.EqualTo(new List<string> { path }));

            var paths = first.hierarchy.ConvertAll(node => node.relativePath);
            Assert.That(paths, Is.EqualTo(new List<string> { "", "Child", "Child/GrandChild" }));
            Assert.That(first.hierarchy[0].depth, Is.EqualTo(0));
            Assert.That(first.hierarchy[1].depth, Is.EqualTo(1));
            Assert.That(first.hierarchy[1].activeSelf, Is.False);
            Assert.That(first.hierarchy[2].activeSelf, Is.True);

            var rootComponents = first.hierarchy[0].components.ConvertAll(component => component.typeName);
            Assert.That(rootComponents, Contains.Item("Transform"));
            Assert.That(rootComponents, Contains.Item("BoxCollider"));
            Assert.That(first.totalComponentCount, Is.EqualTo(5));

            var secondPaths = second.hierarchy.ConvertAll(node => node.relativePath);
            Assert.That(secondPaths, Is.EqualTo(paths), "Repeated inspection must return the same order.");

            AssertEditorStatePreserved();
        }

        [Test]
        public void IdentifiesPrefabVariantAndItsBaseAsset()
        {
            string basePath = CreateRegularPrefab("VariantBase");
            var baseAsset = AssetDatabase.LoadAssetAtPath<GameObject>(basePath);
            // Saving a connected Prefab instance as a new asset is how Unity authors a Variant. The
            // instance is destroyed before inspecting so the scene-preservation assertions below
            // measure the inspection, not this fixture.
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(baseAsset);

            string variantPath = $"{TestFolder}/Variant.prefab";
            PrefabUtility.SaveAsPrefabAsset(instance, variantPath);
            UnityEngine.Object.DestroyImmediate(instance);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(variantPath, Limit);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.prefabKind, Is.EqualTo("variant"));
            Assert.That(result.basePrefabPath, Is.EqualTo(basePath));
            Assert.That(result.rootConnectionStatus, Is.EqualTo("connected"));
            // Ordinal order, not alphabetical-by-eye: '.' (0x2E) sorts before 'B', so
            // "Variant.prefab" precedes "VariantBase.prefab".
            Assert.That(result.editTargetAssetPaths, Is.EqualTo(new List<string> { variantPath, basePath }),
                "Edit targets must be unique and ordinal-sorted.");

            AssertEditorStatePreserved();
        }

        [Test]
        public void ReportsNestedPrefabInstancesAndTheirSourceAssets()
        {
            string nestedPath = CreateRegularPrefab("Nested");
            var nestedAsset = AssetDatabase.LoadAssetAtPath<GameObject>(nestedPath);

            var outerRoot = new GameObject("Outer");
            var nestedInstance = (GameObject)PrefabUtility.InstantiatePrefab(nestedAsset);
            nestedInstance.transform.SetParent(outerRoot.transform, false);

            string outerPath = $"{TestFolder}/Outer.prefab";
            PrefabUtility.SaveAsPrefabAsset(outerRoot, outerPath);
            UnityEngine.Object.DestroyImmediate(outerRoot);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(outerPath, Limit);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.prefabKind, Is.EqualTo("regular"));
            Assert.That(result.nestedPrefabs.Count, Is.EqualTo(1));
            Assert.That(result.nestedPrefabs[0].relativePath, Is.EqualTo("Nested"));
            Assert.That(result.nestedPrefabs[0].sourceAssetPath, Is.EqualTo(nestedPath));
            Assert.That(result.nestedPrefabs[0].sourceGuid, Is.Not.Empty);
            Assert.That(result.nestedPrefabs[0].connectionStatus, Is.EqualTo("connected"));
            Assert.That(result.editTargetAssetPaths, Is.EqualTo(new List<string> { nestedPath, outerPath }));

            var nestedNode = result.hierarchy.Find(node => node.relativePath == "Nested");
            Assert.That(nestedNode, Is.Not.Null);
            Assert.That(nestedNode.isNestedPrefabInstanceRoot, Is.True);
            Assert.That(nestedNode.nestedSourceAssetPath, Is.EqualTo(nestedPath));

            AssertEditorStatePreserved();
        }

        [Test]
        public void ReportsMissingNestedPrefabSourceWithoutFailingTheInspection()
        {
            string nestedPath = CreateRegularPrefab("Disappearing");
            var nestedAsset = AssetDatabase.LoadAssetAtPath<GameObject>(nestedPath);

            var outerRoot = new GameObject("Host");
            var nestedInstance = (GameObject)PrefabUtility.InstantiatePrefab(nestedAsset);
            nestedInstance.transform.SetParent(outerRoot.transform, false);

            string outerPath = $"{TestFolder}/Host.prefab";
            PrefabUtility.SaveAsPrefabAsset(outerRoot, outerPath);
            UnityEngine.Object.DestroyImmediate(outerRoot);

            // Deleting the nested source makes Unity log an import error for the host Prefab - that
            // is exactly the broken state under test, so the Test Framework must not treat those
            // Editor-emitted errors as test failures.
            LogAssert.ignoreFailingMessages = true;
            AssetDatabase.DeleteAsset(nestedPath);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(outerPath, Limit);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.nestedPrefabs.Count, Is.EqualTo(1));
            Assert.That(result.nestedPrefabs[0].connectionStatus, Is.EqualTo("missing_asset"));
            Assert.That(result.nestedPrefabs[0].sourceAssetPath, Is.Null);
            Assert.That(result.editTargetAssetPaths, Is.EqualTo(new List<string> { outerPath }),
                "A missing source must never be offered as an edit target.");
            Assert.That(result.warnings, Is.Not.Empty);

            AssertEditorStatePreserved();
        }

        [Test]
        public void RejectsNonPrefabAssetWithADistinctError()
        {
            string materialPath = $"{TestFolder}/Plain.mat";
            AssetDatabase.CreateAsset(new Material(Shader.Find("Unlit/Color")), materialPath);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(materialPath, Limit);

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("not a Prefab asset"));
            Assert.That(result.hierarchy, Is.Empty);

            AssertEditorStatePreserved();
        }

        [Test]
        public void ReportsMissingAssetDistinctlyFromANonPrefabAsset()
        {
            var result = PrefabInspectionService.InspectPrefabAsset($"{TestFolder}/DoesNotExist.prefab", Limit);

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("Asset not found"));
            Assert.That(result.hierarchy, Is.Empty);

            AssertEditorStatePreserved();
        }

        [Test]
        public void RejectsAnEmptyAssetPath()
        {
            var result = PrefabInspectionService.InspectPrefabAsset("", Limit);

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("required"));

            AssertEditorStatePreserved();
        }

        [Test]
        public void TruncatesLargeHierarchiesDeterministicallyAndReportsRealTotals()
        {
            var root = new GameObject("Wide");
            for (int i = 0; i < 6; i++)
            {
                var child = new GameObject($"Child{i.ToString(System.Globalization.CultureInfo.InvariantCulture)}");
                child.transform.SetParent(root.transform, false);
            }

            string path = $"{TestFolder}/Wide.prefab";
            PrefabUtility.SaveAsPrefabAsset(root, path);
            UnityEngine.Object.DestroyImmediate(root);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(path, 3);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.truncated, Is.True);
            Assert.That(result.hierarchy.Count, Is.EqualTo(3));
            Assert.That(result.totalObjectCount, Is.EqualTo(7), "Totals must describe the whole asset.");
            Assert.That(result.hierarchy.ConvertAll(node => node.relativePath),
                Is.EqualTo(new List<string> { "", "Child0", "Child1" }));
            Assert.That(result.warnings, Is.Not.Empty);

            AssertEditorStatePreserved();
        }

        [Test]
        public void UnloadsIsolatedPrefabContentsEvenWhenInspectionThrows()
        {
            string path = CreateRegularPrefab("Exploding");

            Assert.Throws<InvalidOperationException>(() =>
                PrefabInspectionService.WithPrefabContents<bool>(path, _ => throw new InvalidOperationException("boom")));

            Assert.That(GameObject.Find("Exploding"), Is.Null,
                "Isolated prefab contents must never leak into the active scene.");
            AssertEditorStatePreserved();
        }

        [Test]
        public void SurfacesLoadFailuresAsAFailedResultRatherThanThrowing()
        {
            // A folder is a real asset that is not a Prefab, so LoadPrefabContents cannot open it.
            var result = PrefabInspectionService.InspectPrefabAsset(TestFolder, Limit);

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Is.Not.Null);

            AssertEditorStatePreserved();
        }

        private static string CreateModelAsset(string name)
        {
            string path = $"{TestFolder}/{name}.obj";
            System.IO.File.WriteAllText(path, "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n");
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            AssetDatabase.Refresh();
            return path;
        }

        [Test]
        public void InspectsModelPrefabAssetWithoutInstantiatingOrAddingFalseEditTargets()
        {
            string modelPath = CreateModelAsset("TestModel");

            var result = PrefabInspectionService.InspectPrefabAsset(modelPath, Limit);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.prefabKind, Is.EqualTo("model"));
            Assert.That(result.prefabName, Is.EqualTo("TestModel"));
            Assert.That(result.assetGuid, Is.Not.Empty);
            Assert.That(result.basePrefabPath, Is.Null);
            Assert.That(result.rootConnectionStatus, Is.EqualTo("not_an_instance"));
            Assert.That(result.totalObjectCount, Is.GreaterThanOrEqualTo(1));
            Assert.That(result.editTargetAssetPaths, Is.Empty,
                "Model assets are read-only and must never be offered as edit targets.");
            Assert.That(result.warnings, Is.Not.Empty);

            AssertEditorStatePreserved();
        }

        [Test]
        public void DisambiguatesRelativePathsWhenSiblingsShareName()
        {
            var root = new GameObject("Robot");

            var arm1 = new GameObject("Arm");
            arm1.transform.SetParent(root.transform, false);
            var hand1 = new GameObject("Hand");
            hand1.transform.SetParent(arm1.transform, false);

            var arm2 = new GameObject("Arm");
            arm2.transform.SetParent(root.transform, false);
            var hand2 = new GameObject("Hand");
            hand2.transform.SetParent(arm2.transform, false);

            string path = $"{TestFolder}/Robot.prefab";
            PrefabUtility.SaveAsPrefabAsset(root, path);
            UnityEngine.Object.DestroyImmediate(root);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(path, Limit);

            Assert.That(result.success, Is.True, result.error);
            var paths = result.hierarchy.ConvertAll(node => node.relativePath);
            Assert.That(paths, Is.EqualTo(new List<string> { "", "Arm[0]", "Arm[0]/Hand", "Arm[1]", "Arm[1]/Hand" }));
            Assert.That(result.warnings.Exists(w => w.Contains("disambiguated with indices")), Is.True);

            AssertEditorStatePreserved();
        }

        [Test]
        public void ReportsMissingVariantBasePrefabWithoutFailingTheInspection()
        {
            string basePath = CreateRegularPrefab("BaseForMissing");
            var baseAsset = AssetDatabase.LoadAssetAtPath<GameObject>(basePath);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(baseAsset);

            string variantPath = $"{TestFolder}/VariantWithMissingBase.prefab";
            PrefabUtility.SaveAsPrefabAsset(instance, variantPath);
            UnityEngine.Object.DestroyImmediate(instance);

            LogAssert.ignoreFailingMessages = true;
            AssetDatabase.DeleteAsset(basePath);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(variantPath, Limit);

            Assert.That(result.success, Is.False);
            Assert.That(result.error, Does.Contain("broken: Unity reports its Prefab source as missing"));
            Assert.That(result.hierarchy, Is.Empty);

            AssertEditorStatePreserved();
        }

        [Test]
        public void ExcludesNestedModelAssetsFromEditTargets()
        {
            string modelPath = CreateModelAsset("ShieldModel");
            var modelAsset = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);

            var outerRoot = new GameObject("Hero");
            var nestedModel = (GameObject)PrefabUtility.InstantiatePrefab(modelAsset);
            nestedModel.name = "Shield";
            nestedModel.transform.SetParent(outerRoot.transform, false);

            string outerPath = $"{TestFolder}/Hero.prefab";
            PrefabUtility.SaveAsPrefabAsset(outerRoot, outerPath);
            UnityEngine.Object.DestroyImmediate(outerRoot);
            AssetDatabase.Refresh();

            var result = PrefabInspectionService.InspectPrefabAsset(outerPath, Limit);

            Assert.That(result.success, Is.True, result.error);
            Assert.That(result.nestedPrefabs.Count, Is.EqualTo(1));
            Assert.That(result.nestedPrefabs[0].name, Is.EqualTo("Shield"));
            Assert.That(result.nestedPrefabs[0].sourceAssetPath, Is.EqualTo(modelPath));
            Assert.That(result.nestedPrefabs[0].connectionStatus, Is.EqualTo("connected"));
            Assert.That(result.editTargetAssetPaths, Is.EqualTo(new List<string> { outerPath }),
                "Nested model assets must not be added to edit targets.");

            AssertEditorStatePreserved();
        }
    }
}
