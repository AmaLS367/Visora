import json


def _skinned_mesh_diagnostics_code(mesh_renderer_path: str) -> str:
    """
    Generates C# script to inspect a SkinnedMeshRenderer component, sharedMesh details,
    bones array, rootBone, materials/shaders, submeshes, and local/world bounding boxes.
    """
    path_literal = json.dumps(mesh_renderer_path)
    return f"""
var targetPath = {path_literal};
var targetGo = UnityEngine.GameObject.Find(targetPath);
if (targetGo == null)
{{
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "success", false }},
        {{ "error", "GameObject not found at hierarchy path: " + targetPath }},
    }};
}}

var smr = targetGo.GetComponent<UnityEngine.SkinnedMeshRenderer>();
if (smr == null)
{{
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "success", false }},
        {{ "error", "No SkinnedMeshRenderer component found on GameObject at: " + targetPath }},
    }};
}}

var sharedMesh = smr.sharedMesh;
bool hasSharedMesh = sharedMesh != null;
string meshName = hasSharedMesh ? sharedMesh.name : null;
int vertexCount = hasSharedMesh ? sharedMesh.vertexCount : 0;
int subMeshCount = hasSharedMesh ? sharedMesh.subMeshCount : 0;
int blendShapeCount = hasSharedMesh ? sharedMesh.blendShapeCount : 0;
int bindPosesCount = (hasSharedMesh && sharedMesh.bindposes != null) ? sharedMesh.bindposes.Length : 0;

var submeshesList = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
if (hasSharedMesh)
{{
    for (int i = 0; i < subMeshCount; i++)
    {{
        submeshesList.Add(new System.Collections.Generic.Dictionary<string, object>
        {{
            {{ "index", i }},
            {{ "indexCount", (int)sharedMesh.GetIndexCount(i) }},
            {{ "topology", sharedMesh.GetTopology(i).ToString() }},
        }});
    }}
}}

var blendshapesList = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
if (hasSharedMesh)
{{
    for (int i = 0; i < blendShapeCount; i++)
    {{
        blendshapesList.Add(new System.Collections.Generic.Dictionary<string, object>
        {{
            {{ "index", i }},
            {{ "name", sharedMesh.GetBlendShapeName(i) }},
            {{ "weight", (double)smr.GetBlendShapeWeight(i) }},
        }});
    }}
}}

var bonesList = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
var bones = smr.bones;
if (bones != null)
{{
    for (int i = 0; i < bones.Length; i++)
    {{
        var b = bones[i];
        if (b == null)
        {{
            bonesList.Add(new System.Collections.Generic.Dictionary<string, object>
            {{
                {{ "index", i }},
                {{ "isNull", true }},
                {{ "name", null }},
                {{ "path", null }},
                {{ "lossyScale", null }},
                {{ "position", null }},
            }});
        }}
        else
        {{
            string bPath = b.name;
            var cur = b.parent;
            while (cur != null)
            {{
                bPath = cur.name + "/" + bPath;
                cur = cur.parent;
            }}
            bonesList.Add(new System.Collections.Generic.Dictionary<string, object>
            {{
                {{ "index", i }},
                {{ "isNull", false }},
                {{ "name", b.name }},
                {{ "path", bPath }},
                {{ "lossyScale", new double[] {{ b.lossyScale.x, b.lossyScale.y, b.lossyScale.z }} }},
                {{ "position", new double[] {{ b.position.x, b.position.y, b.position.z }} }},
            }});
        }}
    }}
}}

var rootBone = smr.rootBone;
string rootBonePath = null;
double[] rootBoneScale = null;
if (rootBone != null)
{{
    rootBonePath = rootBone.name;
    var cur = rootBone.parent;
    while (cur != null)
    {{
        rootBonePath = cur.name + "/" + rootBonePath;
        cur = cur.parent;
    }}
    rootBoneScale = new double[] {{ rootBone.lossyScale.x, rootBone.lossyScale.y, rootBone.lossyScale.z }};
}}

var materialsList = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
var sharedMats = smr.sharedMaterials;
if (sharedMats != null)
{{
    for (int i = 0; i < sharedMats.Length; i++)
    {{
        var m = sharedMats[i];
        if (m == null)
        {{
            materialsList.Add(new System.Collections.Generic.Dictionary<string, object>
            {{
                {{ "index", i }},
                {{ "isMissing", true }},
                {{ "name", null }},
                {{ "shaderName", null }},
                {{ "isSupported", false }},
                {{ "isErrorShader", false }},
                {{ "mainTextureName", null }},
                {{ "hasMainTexture", false }},
            }});
        }}
        else
        {{
            var sh = m.shader;
            string shName = sh != null ? sh.name : null;
            bool isSupp = sh != null ? sh.isSupported : false;
            bool isErrSh = sh == null || shName == "Hidden/InternalErrorShader" || !isSupp;
            var tex = m.mainTexture;
            materialsList.Add(new System.Collections.Generic.Dictionary<string, object>
            {{
                {{ "index", i }},
                {{ "isMissing", false }},
                {{ "name", m.name }},
                {{ "shaderName", shName }},
                {{ "isSupported", isSupp }},
                {{ "isErrorShader", isErrSh }},
                {{ "mainTextureName", tex != null ? tex.name : null }},
                {{ "hasMainTexture", tex != null }},
            }});
        }}
    }}
}}

var localB = smr.localBounds;
var worldB = smr.bounds;

return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "success", true }},
    {{ "targetPath", targetPath }},
    {{ "hasSharedMesh", hasSharedMesh }},
    {{ "meshName", meshName }},
    {{ "vertexCount", vertexCount }},
    {{ "subMeshCount", subMeshCount }},
    {{ "blendShapeCount", blendShapeCount }},
    {{ "bindPosesCount", bindPosesCount }},
    {{ "submeshes", submeshesList }},
    {{ "blendshapes", blendshapesList }},
    {{ "bones", bonesList }},
    {{ "hasRootBone", rootBone != null }},
    {{ "rootBonePath", rootBonePath }},
    {{ "rootBoneScale", rootBoneScale }},
    {{ "materials", materialsList }},
    {{ "updateWhenOffscreen", smr.updateWhenOffscreen }},
    {{ "localCenter", new double[] {{ localB.center.x, localB.center.y, localB.center.z }} }},
    {{ "localSize", new double[] {{ localB.size.x, localB.size.y, localB.size.z }} }},
    {{ "worldCenter", new double[] {{ worldB.center.x, worldB.center.y, worldB.center.z }} }},
    {{ "worldSize", new double[] {{ worldB.size.x, worldB.size.y, worldB.size.z }} }},
}};
"""
