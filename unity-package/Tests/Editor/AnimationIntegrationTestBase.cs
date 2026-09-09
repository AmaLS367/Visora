using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Tests
{
    public abstract class AnimationIntegrationTestBase
    {
        protected const string TestAssetFolder = "Assets/VisoraIntegrationTests";
        private readonly List<GameObject> sceneObjects = new List<GameObject>();

        protected GameObject Track(GameObject go)
        {
            sceneObjects.Add(go);
            return go;
        }

        protected AnimationClip CreateClip(string fileName, float frameRate = 30f)
        {
            if (!AssetDatabase.IsValidFolder(TestAssetFolder))
            {
                AssetDatabase.CreateFolder("Assets", "VisoraIntegrationTests");
            }

            string path = $"{TestAssetFolder}/{fileName}";
            AssetDatabase.DeleteAsset(path);
            var clip = new AnimationClip { frameRate = frameRate };
            AssetDatabase.CreateAsset(clip, path);
            return clip;
        }

        protected static void SetCurve(AnimationClip clip, string path, string property, params Keyframe[] keys)
        {
            var binding = EditorCurveBinding.FloatCurve(path, typeof(Transform), property);
            AnimationUtility.SetEditorCurve(clip, binding, new AnimationCurve(keys));
        }

        protected static AnimationCurve GetCurve(AnimationClip clip, string path, string property)
        {
            var binding = EditorCurveBinding.FloatCurve(path, typeof(Transform), property);
            return AnimationUtility.GetEditorCurve(clip, binding);
        }

        protected static string AssetPath(AnimationClip clip)
        {
            return AssetDatabase.GetAssetPath(clip);
        }

        protected static byte[] ReadAssetBytes(AnimationClip clip)
        {
            AssetDatabase.SaveAssetIfDirty(clip);
            return File.ReadAllBytes(Path.GetFullPath(AssetPath(clip)));
        }

        protected static (GameObject root, Transform upper, Transform lower, Transform end) CreateLegChain(
            string rootName,
            Vector3 upperWorldPosition)
        {
            var root = new GameObject(rootName);
            var upper = new GameObject("LeftUpperLeg").transform;
            var lower = new GameObject("LeftLowerLeg").transform;
            var end = new GameObject("LeftFoot").transform;

            upper.SetParent(root.transform, false);
            lower.SetParent(upper, false);
            end.SetParent(lower, false);
            upper.position = upperWorldPosition;
            lower.localPosition = Vector3.right;
            end.localPosition = Vector3.right;
            return (root, upper, lower, end);
        }

        protected static void AddIdentityRotationCurves(AnimationClip clip, string path)
        {
            SetCurve(clip, path, "m_LocalRotation.x", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(clip, path, "m_LocalRotation.y", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(clip, path, "m_LocalRotation.z", new Keyframe(0f, 0f), new Keyframe(1f, 0f));
            SetCurve(clip, path, "m_LocalRotation.w", new Keyframe(0f, 1f), new Keyframe(1f, 1f));
        }

        [NUnit.Framework.TearDown]
        public void TearDownIntegrationState()
        {
            if (AnimationMode.InAnimationMode())
            {
                AnimationMode.StopAnimationMode();
            }
            Undo.ClearAll();
            foreach (var go in sceneObjects)
            {
                if (go != null) Object.DestroyImmediate(go);
            }
            sceneObjects.Clear();
            AssetDatabase.DeleteAsset(TestAssetFolder);
            AssetDatabase.Refresh();
        }
    }
}
