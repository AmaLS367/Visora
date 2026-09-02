using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class ProjectPathsResult
    {
        public bool success;
        public string error;
        public string dataPath;
        public string projectPath;
        public string assetsPath;
    }

    [Serializable]
    public class AssetImportResult
    {
        public bool success;
        public string error;
        public string assetPath;
        public List<string> importedObjects = new List<string>();
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class NativeModelImporterInfo
    {
        public string animation_type;
        public int clip_count;
        public string material_import_mode;
        public bool import_normals;
        public double global_scale;
        public string mesh_compression;
    }

    [Serializable]
    public class AssetInspectResult
    {
        public bool success;
        public string error;
        public string asset_path;
        public string asset_type;
        public NativeModelImporterInfo model_importer_info;
        public int submesh_count;
        public List<string> materials = new List<string>();
        public List<string> textures = new List<string>();
        public List<string> animation_clips = new List<string>();
        public List<string> hierarchy_tree = new List<string>();
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class AssetInstantiateResult
    {
        public bool success;
        public string error;
        public string game_object_name;
        public string game_object_path;
        public int instance_id;
        public List<float> world_position = new List<float>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Service for managing project asset paths, synchronous asset importing,
    /// model inspection, and scene instantiation on the Unity Editor side.
    /// </summary>
    public static class AssetManagementService
    {
        public static ProjectPathsResult GetProjectPaths()
        {
            try
            {
                string dataPath = Application.dataPath.Replace("\\", "/");
                string projectPath = Directory.GetParent(Application.dataPath)?.FullName?.Replace("\\", "/") ?? dataPath;
                return new ProjectPathsResult
                {
                    success = true,
                    dataPath = dataPath,
                    projectPath = projectPath,
                    assetsPath = dataPath
                };
            }
            catch (Exception ex)
            {
                return new ProjectPathsResult
                {
                    success = false,
                    error = $"Failed to get project paths: {ex.Message}"
                };
            }
        }

        public static AssetImportResult ImportAsset(string assetPath)
        {
            var result = new AssetImportResult { assetPath = assetPath };
            try
            {
                string normalizedPath = (assetPath ?? "").Replace("\\", "/");
                if (string.IsNullOrEmpty(normalizedPath))
                {
                    AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                    result.success = true;
                    return result;
                }

                if (normalizedPath.EndsWith(".unitypackage", StringComparison.OrdinalIgnoreCase))
                {
                    AssetDatabase.ImportPackage(normalizedPath, false);
                }
                else
                {
                    AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                    AssetDatabase.ImportAsset(normalizedPath, ImportAssetOptions.ForceUpdate);
                }

                var mainObj = AssetDatabase.LoadMainAssetAtPath(normalizedPath);
                if (mainObj != null)
                {
                    result.importedObjects.Add(normalizedPath);
                }

                result.success = true;
                return result;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Asset import failed: {ex.Message}";
                return result;
            }
        }

        public static AssetInspectResult InspectAsset(string assetPath)
        {
            var result = new AssetInspectResult { asset_path = assetPath };
            try
            {
                string normalizedPath = (assetPath ?? "").Replace("\\", "/");
                var mainAsset = AssetDatabase.LoadMainAssetAtPath(normalizedPath);
                if (mainAsset == null)
                {
                    result.success = false;
                    result.error = $"Asset not found at path: {normalizedPath}";
                    return result;
                }

                result.asset_type = mainAsset.GetType().Name;

                var importer = AssetImporter.GetAtPath(normalizedPath) as ModelImporter;
                if (importer != null)
                {
                    result.model_importer_info = new NativeModelImporterInfo
                    {
                        animation_type = importer.animationType.ToString(),
                        clip_count = importer.defaultClipAnimations != null ? importer.defaultClipAnimations.Length : 0,
                        material_import_mode = importer.materialImportMode.ToString(),
                        import_normals = importer.importNormals != ModelImporterNormals.None,
                        global_scale = importer.globalScale,
                        mesh_compression = importer.meshCompression.ToString()
                    };
                }

                if (mainAsset is GameObject go)
                {
                    var renderers = go.GetComponentsInChildren<Renderer>(true);
                    foreach (var r in renderers)
                    {
                        if (r is SkinnedMeshRenderer smr && smr.sharedMesh != null)
                        {
                            result.submesh_count += smr.sharedMesh.subMeshCount;
                        }
                        else if (r is MeshRenderer)
                        {
                            var mf = r.GetComponent<MeshFilter>();
                            if (mf != null && mf.sharedMesh != null)
                            {
                                result.submesh_count += mf.sharedMesh.subMeshCount;
                            }
                        }

                        foreach (var mat in r.sharedMaterials)
                        {
                            if (mat != null && !result.materials.Contains(mat.name))
                            {
                                result.materials.Add(mat.name);
                            }
                        }
                    }

                    var transforms = go.GetComponentsInChildren<Transform>(true);
                    foreach (var t in transforms)
                    {
                        result.hierarchy_tree.Add(t.name);
                    }
                }

                var allSubAssets = AssetDatabase.LoadAllAssetsAtPath(normalizedPath);
                foreach (var sub in allSubAssets)
                {
                    if (sub is AnimationClip clip && !result.animation_clips.Contains(clip.name))
                    {
                        result.animation_clips.Add(clip.name);
                    }
                    else if (sub is Material m && !result.materials.Contains(m.name))
                    {
                        result.materials.Add(m.name);
                    }
                    else if (sub is Texture t && !result.textures.Contains(t.name))
                    {
                        result.textures.Add(t.name);
                    }
                }

                result.success = true;
                return result;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Asset inspection failed: {ex.Message}";
                return result;
            }
        }

        public static AssetInstantiateResult InstantiateAsset(
            string assetPath,
            string parentPath,
            float[] position,
            float[] rotation,
            float[] scale,
            string name)
        {
            var result = new AssetInstantiateResult();
            try
            {
                string normalizedPath = (assetPath ?? "").Replace("\\", "/");
                var assetObj = AssetDatabase.LoadMainAssetAtPath(normalizedPath);
                if (assetObj == null)
                {
                    result.success = false;
                    result.error = $"Asset not found at path: {normalizedPath}";
                    return result;
                }

                GameObject instance = null;
                if (assetObj is GameObject prefab)
                {
                    instance = PrefabUtility.InstantiatePrefab(prefab) as GameObject;
                    if (instance == null)
                    {
                        instance = UnityEngine.Object.Instantiate(prefab);
                    }
                }
                else
                {
                    result.success = false;
                    result.error = $"Asset at path is not a GameObject or Prefab: {normalizedPath}";
                    return result;
                }

                Undo.RegisterCreatedObjectUndo(instance, "Visora Instantiate Asset");

                if (!string.IsNullOrEmpty(name))
                {
                    instance.name = name;
                }

                if (position != null && position.Length >= 3)
                {
                    instance.transform.position = new Vector3(position[0], position[1], position[2]);
                }
                if (rotation != null && rotation.Length >= 3)
                {
                    instance.transform.eulerAngles = new Vector3(rotation[0], rotation[1], rotation[2]);
                }
                if (scale != null && scale.Length >= 3)
                {
                    instance.transform.localScale = new Vector3(scale[0], scale[1], scale[2]);
                }

                if (!string.IsNullOrEmpty(parentPath))
                {
                    var parent = GameObject.Find(parentPath);
                    if (parent != null)
                    {
                        instance.transform.SetParent(parent.transform, true);
                    }
                }

                string fullPath = instance.name;
                var curr = instance.transform.parent;
                while (curr != null)
                {
                    fullPath = curr.name + "/" + fullPath;
                    curr = curr.parent;
                }

                result.success = true;
                result.game_object_name = instance.name;
                result.game_object_path = fullPath;
                result.instance_id = instance.GetInstanceID();
                result.world_position = new List<float>
                {
                    instance.transform.position.x,
                    instance.transform.position.y,
                    instance.transform.position.z
                };
                return result;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Instantiation failed: {ex.Message}";
                return result;
            }
        }
    }
}
