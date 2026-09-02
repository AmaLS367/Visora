"""
C# script templates for asset discovery, path querying, synchronous importing,
ModelImporter inspection, and scene instantiation in Unity Editor.
"""

from __future__ import annotations


def _get_project_paths_code() -> str:
    """Returns C# code to query project root and Assets paths."""
    return """
string dataPath = UnityEngine.Application.dataPath;
string projectPath = System.IO.Directory.GetParent(dataPath).FullName;
return new Dictionary<string, object> {
    {"success", true},
    {"dataPath", dataPath.Replace("\\\\", "/")},
    {"projectPath", projectPath.Replace("\\\\", "/")},
    {"assetsPath", dataPath.Replace("\\\\", "/")}
};
"""


def _import_asset_code(asset_path: str, *, allow_unitypackage: bool = False) -> str:
    """Returns C# code to refresh AssetDatabase and import an asset."""
    escaped = asset_path.replace('"', '\\"').replace("\\", "/")
    package_allowed = str(allow_unitypackage).lower()
    return f"""
string targetPath = "{escaped}";
if (targetPath.EndsWith(".unitypackage", StringComparison.OrdinalIgnoreCase)) {{
    if (!{package_allowed}) {{
        return new Dictionary<string, object> {{
            {{"success", false}},
            {{"error", "Unity package import requires explicit allowUnityPackage opt-in."}}
        }};
    }}
    var beforePaths = new HashSet<string>(UnityEditor.AssetDatabase.GetAllAssetPaths());
    UnityEditor.AssetDatabase.ImportPackage(targetPath, false);
    UnityEditor.AssetDatabase.Refresh(UnityEditor.ImportAssetOptions.ForceSynchronousImport);
    var packageImportedPaths = new List<string>();
    foreach (var path in UnityEditor.AssetDatabase.GetAllAssetPaths()) {{
        if (!beforePaths.Contains(path) && path.StartsWith("Assets/")) {{
            packageImportedPaths.Add(path);
        }}
    }}
    if (packageImportedPaths.Count == 0) {{
        return new Dictionary<string, object> {{
            {{"success", false}},
            {{"error", "Unity package import created no assets."}}
        }};
    }}
    return new Dictionary<string, object> {{
        {{"success", true}},
        {{"assetPath", targetPath}},
        {{"importedObjects", packageImportedPaths}}
    }};
}} else {{
    UnityEditor.AssetDatabase.Refresh(UnityEditor.ImportAssetOptions.ForceSynchronousImport);
    if (!string.IsNullOrEmpty(targetPath)) {{
        UnityEditor.AssetDatabase.ImportAsset(targetPath, UnityEditor.ImportAssetOptions.ForceUpdate);
    }}
}}
UnityEngine.Object mainObj = UnityEditor.AssetDatabase.LoadMainAssetAtPath(targetPath);
var importedPaths = new List<string>();
if (mainObj != null) {{
    importedPaths.Add(targetPath);
}}
if (importedPaths.Count == 0) {{
    return new Dictionary<string, object> {{
        {{"success", false}},
        {{"error", "Asset was not registered by Unity: " + targetPath}}
    }};
}}
return new Dictionary<string, object> {{
    {{"success", true}},
    {{"assetPath", targetPath}},
    {{"importedObjects", importedPaths}}
}};
"""


def _inspect_asset_code(asset_path: str) -> str:
    """Returns C# code to deeply inspect an asset, its importer settings, meshes, and clips."""
    escaped = asset_path.replace('"', '\\"').replace("\\", "/")
    return f"""
string targetPath = "{escaped}";
UnityEngine.Object mainAsset = UnityEditor.AssetDatabase.LoadMainAssetAtPath(targetPath);
if (mainAsset == null) {{
    return new Dictionary<string, object> {{
        {{"success", false}},
        {{"error", "Asset not found at path: " + targetPath}}
    }};
}}
string assetType = mainAsset.GetType().Name;
UnityEditor.ModelImporter importer = UnityEditor.AssetImporter.GetAtPath(targetPath) as UnityEditor.ModelImporter;
Dictionary<string, object> importerInfo = null;
if (importer != null) {{
    importerInfo = new Dictionary<string, object> {{
        {{"animation_type", importer.animationType.ToString()}},
        {{"clip_count", importer.defaultClipAnimations != null ? importer.defaultClipAnimations.Length : 0}},
        {{"material_import_mode", importer.materialImportMode.ToString()}},
        {{"import_normals", importer.importNormals != UnityEditor.ModelImporterNormals.None}},
        {{"global_scale", (double)importer.globalScale}},
        {{"mesh_compression", importer.meshCompression.ToString()}}
    }};
}}
int submeshCount = 0;
var materialList = new List<string>();
var textureList = new List<string>();
var clipList = new List<string>();
var hierarchyList = new List<string>();

if (mainAsset is UnityEngine.GameObject go) {{
    var renderers = go.GetComponentsInChildren<UnityEngine.Renderer>(true);
    foreach (var r in renderers) {{
        if (r is UnityEngine.SkinnedMeshRenderer smr && smr.sharedMesh != null) {{
            submeshCount += smr.sharedMesh.subMeshCount;
        }} else if (r is UnityEngine.MeshRenderer) {{
            var mf = r.GetComponent<UnityEngine.MeshFilter>();
            if (mf != null && mf.sharedMesh != null) {{
                submeshCount += mf.sharedMesh.subMeshCount;
            }}
        }}
        foreach (var mat in r.sharedMaterials) {{
            if (mat != null && !materialList.Contains(mat.name)) {{
                materialList.Add(mat.name);
            }}
        }}
    }}
    var transforms = go.GetComponentsInChildren<UnityEngine.Transform>(true);
    foreach (var t in transforms) {{
        hierarchyList.Add(t.name);
    }}
}}
var allSubAssets = UnityEditor.AssetDatabase.LoadAllAssetsAtPath(targetPath);
foreach (var sub in allSubAssets) {{
    if (sub is UnityEngine.AnimationClip clip && !clipList.Contains(clip.name)) {{
        clipList.Add(clip.name);
    }} else if (sub is UnityEngine.Material m && !materialList.Contains(m.name)) {{
        materialList.Add(m.name);
    }} else if (sub is UnityEngine.Texture t && !textureList.Contains(t.name)) {{
        textureList.Add(t.name);
    }}
}}
return new Dictionary<string, object> {{
    {{"success", true}},
    {{"asset_path", targetPath}},
    {{"asset_type", assetType}},
    {{"model_importer_info", importerInfo}},
    {{"submesh_count", submeshCount}},
    {{"materials", materialList}},
    {{"textures", textureList}},
    {{"animation_clips", clipList}},
    {{"hierarchy_tree", hierarchyList}}
}};
"""


def _instantiate_asset_code(  # noqa: PLR0913
    asset_path: str,
    parent_path: str | None = None,
    position: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
    name: str | None = None,
) -> str:
    """Returns C# code to instantiate a prefab/model asset into the active scene with Undo."""
    escaped_asset = asset_path.replace('"', '\\"').replace("\\", "/")
    escaped_parent = (parent_path or "").replace('"', '\\"')
    escaped_name = (name or "").replace('"', '\\"')

    pos = position or [0.0, 0.0, 0.0]
    rot = rotation or [0.0, 0.0, 0.0]
    scl = scale or [1.0, 1.0, 1.0]

    parent_assignment = ""
    if parent_path:
        parent_assignment = f"""
var parentObj = UnityEngine.GameObject.Find("{escaped_parent}");
if (parentObj != null) {{
    instance.transform.SetParent(parentObj.transform, true);
}}
"""

    name_assignment = ""
    if name:
        name_assignment = f'instance.name = "{escaped_name}";'

    return f"""
string targetPath = "{escaped_asset}";
UnityEngine.Object assetObj = UnityEditor.AssetDatabase.LoadMainAssetAtPath(targetPath);
if (assetObj == null) {{
    return new Dictionary<string, object> {{
        {{"success", false}},
        {{"error", "Asset not found at path: " + targetPath}}
    }};
}}
UnityEngine.GameObject instance = null;
if (assetObj is UnityEngine.GameObject prefab) {{
    instance = UnityEditor.PrefabUtility.InstantiatePrefab(prefab) as UnityEngine.GameObject;
    if (instance == null) {{
        instance = UnityEngine.Object.Instantiate(prefab);
    }}
}} else {{
    return new Dictionary<string, object> {{
        {{"success", false}},
        {{"error", "Asset at path is not a GameObject or Prefab: " + targetPath}}
    }};
}}
UnityEditor.Undo.RegisterCreatedObjectUndo(instance, "Visora Instantiate Asset");
{name_assignment}
instance.transform.position = new UnityEngine.Vector3({pos[0]}f, {pos[1]}f, {pos[2]}f);
instance.transform.eulerAngles = new UnityEngine.Vector3({rot[0]}f, {rot[1]}f, {rot[2]}f);
instance.transform.localScale = new UnityEngine.Vector3({scl[0]}f, {scl[1]}f, {scl[2]}f);
{parent_assignment}
string fullPath = instance.name;
var curr = instance.transform.parent;
while (curr != null) {{
    fullPath = curr.name + "/" + fullPath;
    curr = curr.parent;
}}
return new Dictionary<string, object> {{
    {{"success", true}},
    {{"game_object_name", instance.name}},
    {{"game_object_path", fullPath}},
    {{"instance_id", instance.GetInstanceID()}},
    {{"world_position", new List<double> {{instance.transform.position.x, instance.transform.position.y, instance.transform.position.z}}}}
}};
"""
