import json


def _inspect_clip_code(clip_path: str) -> str:
    """
    Generates C# script to inspect an AnimationClip in Unity Editor via AssetDatabase and AnimationUtility.
    """
    path_literal = json.dumps(clip_path)
    return f"""
var clipPath = {path_literal};
var clip = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.AnimationClip>(clipPath);

if (clip == null)
{{
    // Try finding by GUID or name if exact path failed
    var guids = UnityEditor.AssetDatabase.FindAssets(System.IO.Path.GetFileNameWithoutExtension(clipPath) + " t:AnimationClip");
    if (guids.Length > 0)
    {{
        var foundPath = UnityEditor.AssetDatabase.GUIDToAssetPath(guids[0]);
        clip = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.AnimationClip>(foundPath);
        if (clip != null)
        {{
            clipPath = foundPath;
        }}
    }}
}}

if (clip == null)
{{
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "success", false }},
        {{ "error", "AnimationClip not found at path: " + {path_literal} }},
    }};
}}

var bindingsList = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
var curveBindings = UnityEditor.AnimationUtility.GetCurveBindings(clip);

foreach (var b in curveBindings)
{{
    var curve = UnityEditor.AnimationUtility.GetEditorCurve(clip, b);
    int keyCount = curve != null ? curve.keys.Length : 0;
    float minVal = float.MaxValue;
    float maxVal = float.MinValue;
    float startVal = 0f;
    float endVal = 0f;
    bool isConstant = true;

    if (curve != null && keyCount > 0)
    {{
        startVal = curve.keys[0].value;
        endVal = curve.keys[keyCount - 1].value;
        float firstVal = startVal;

        for (int i = 0; i < keyCount; i++)
        {{
            float val = curve.keys[i].value;
            if (val < minVal) minVal = val;
            if (val > maxVal) maxVal = val;
            if (System.Math.Abs(val - firstVal) > 0.0001f)
            {{
                isConstant = false;
            }}
        }}
    }}
    else
    {{
        minVal = 0f;
        maxVal = 0f;
    }}

    string propName = b.propertyName ?? "";
    string curveType = "unknown";
    if (propName.StartsWith("m_LocalPosition") || propName.Contains("Position"))
    {{
        curveType = "position";
    }}
    else if (propName.StartsWith("m_LocalRotation") || propName.StartsWith("localEulerAngles") || propName.Contains("Rotation"))
    {{
        curveType = "rotation";
    }}
    else if (propName.StartsWith("m_LocalScale") || propName.Contains("Scale"))
    {{
        curveType = "scale";
    }}
    else
    {{
        curveType = "float_property";
    }}

    var bDict = new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "path", b.path ?? "" }},
        {{ "propertyName", propName }},
        {{ "typeName", b.type != null ? b.type.FullName : "UnityEngine.Transform" }},
        {{ "curveType", curveType }},
        {{ "keyframeCount", keyCount }},
        {{ "minValue", minVal != float.MaxValue ? (object)minVal : null }},
        {{ "maxValue", maxVal != float.MinValue ? (object)maxVal : null }},
        {{ "startValue", keyCount > 0 ? (object)startVal : null }},
        {{ "endValue", keyCount > 0 ? (object)endVal : null }},
        {{ "isConstant", isConstant }},
    }};
    bindingsList.Add(bDict);
}}

// Also check object reference curves (e.g. sprite animations)
var objectBindings = UnityEditor.AnimationUtility.GetObjectReferenceCurveBindings(clip);
foreach (var ob in objectBindings)
{{
    var objCurve = UnityEditor.AnimationUtility.GetObjectReferenceCurve(clip, ob);
    int keyCount = objCurve != null ? objCurve.Length : 0;
    var obDict = new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "path", ob.path ?? "" }},
        {{ "propertyName", ob.propertyName ?? "" }},
        {{ "typeName", ob.type != null ? ob.type.FullName : "UnityEngine.Object" }},
        {{ "curveType", "reference" }},
        {{ "keyframeCount", keyCount }},
        {{ "minValue", null }},
        {{ "maxValue", null }},
        {{ "startValue", null }},
        {{ "endValue", null }},
        {{ "isConstant", keyCount <= 1 }},
    }};
    bindingsList.Add(obDict);
}}

// Extract animation events
var eventsList = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
var events = UnityEditor.AnimationUtility.GetAnimationEvents(clip);
foreach (var evt in events)
{{
    var eDict = new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "time", evt.time }},
        {{ "functionName", evt.functionName ?? "" }},
        {{ "stringParam", evt.stringParameter ?? "" }},
        {{ "floatParam", evt.floatParameter }},
        {{ "intParam", evt.intParameter }},
    }};
    eventsList.Add(eDict);
}}

return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "success", true }},
    {{ "clipName", clip.name }},
    {{ "clipPath", clipPath }},
    {{ "length", clip.length }},
    {{ "fps", clip.frameRate }},
    {{ "loopTime", clip.isLooping }},
    {{ "wrapMode", clip.wrapMode.ToString() }},
    {{ "isLegacy", clip.legacy }},
    {{ "hasRootMotion", clip.hasRootMotion }},
    {{ "curvesCount", bindingsList.Count }},
    {{ "eventsCount", eventsList.Count }},
    {{ "bindings", bindingsList }},
    {{ "events", eventsList }},
}};
"""


def _sample_clip_code(
    target_game_object_path: str,
    clip_path: str,
    time: float,
    restore_pose_after: bool = True,
    tracked_bone_paths: list[str] | None = None,
) -> str:
    """
    Generates C# script to sample an AnimationClip at a specific timestamp and retrieve transform poses.
    """
    target_path_literal = json.dumps(target_game_object_path)
    clip_path_literal = json.dumps(clip_path)
    tracked_literal = json.dumps(tracked_bone_paths) if tracked_bone_paths else "null"
    restore_literal = "true" if restore_pose_after else "false"

    return f"""
var targetPath = {target_path_literal};
var clipPath = {clip_path_literal};
var sampleTime = {time}f;
var restorePose = {restore_literal};
string[] trackedBones = {tracked_literal};

var targetGo = UnityEngine.GameObject.Find(targetPath);
if (targetGo == null)
{{
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "success", false }},
        {{ "error", "Target GameObject not found at hierarchy path: " + targetPath }},
    }};
}}

var clip = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.AnimationClip>(clipPath);
if (clip == null)
{{
    var guids = UnityEditor.AssetDatabase.FindAssets(System.IO.Path.GetFileNameWithoutExtension(clipPath) + " t:AnimationClip");
    if (guids.Length > 0)
    {{
        clip = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.AnimationClip>(UnityEditor.AssetDatabase.GUIDToAssetPath(guids[0]));
    }}
}}

if (clip == null)
{{
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "success", false }},
        {{ "error", "AnimationClip not found at path: " + clipPath }},
    }};
}}

// Record initial rest transform states
var transformsToSnapshot = new System.Collections.Generic.List<UnityEngine.Transform>();
if (trackedBones != null && trackedBones.Length > 0)
{{
    foreach (var bPath in trackedBones)
    {{
        var t = string.IsNullOrEmpty(bPath) ? targetGo.transform : targetGo.transform.Find(bPath);
        if (t != null && !transformsToSnapshot.Contains(t))
        {{
            transformsToSnapshot.Add(t);
        }}
    }}
}}
else
{{
    transformsToSnapshot.AddRange(targetGo.GetComponentsInChildren<UnityEngine.Transform>(true));
}}

var restPos = new System.Collections.Generic.Dictionary<UnityEngine.Transform, UnityEngine.Vector3>();
var restRot = new System.Collections.Generic.Dictionary<UnityEngine.Transform, UnityEngine.Quaternion>();
var restScale = new System.Collections.Generic.Dictionary<UnityEngine.Transform, UnityEngine.Vector3>();

foreach (var t in transformsToSnapshot)
{{
    restPos[t] = t.localPosition;
    restRot[t] = t.localRotation;
    restScale[t] = t.localScale;
}}

var restRootLocalPos = targetGo.transform.localPosition;

// Sample the animation clip on the target GameObject
clip.SampleAnimation(targetGo, sampleTime);

// Extract sampled transforms
var sampledDict = new System.Collections.Generic.Dictionary<string, object>();
foreach (var t in transformsToSnapshot)
{{
    string relativePath = "";
    if (t == targetGo.transform)
    {{
        relativePath = "";
    }}
    else
    {{
        var current = t;
        var parts = new System.Collections.Generic.List<string>();
        while (current != null && current != targetGo.transform)
        {{
            parts.Insert(0, current.name);
            current = current.parent;
        }}
        relativePath = string.Join("/", parts);
    }}

    var tData = new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "path", relativePath }},
        {{ "name", t.name }},
        {{ "localPosition", new float[] {{ t.localPosition.x, t.localPosition.y, t.localPosition.z }} }},
        {{ "localRotationEuler", new float[] {{ t.localEulerAngles.x, t.localEulerAngles.y, t.localEulerAngles.z }} }},
        {{ "localScale", new float[] {{ t.localScale.x, t.localScale.y, t.localScale.z }} }},
        {{ "worldPosition", new float[] {{ t.position.x, t.position.y, t.position.z }} }},
        {{ "worldRotationEuler", new float[] {{ t.eulerAngles.x, t.eulerAngles.y, t.eulerAngles.z }} }},
        {{ "worldScale", new float[] {{ t.lossyScale.x, t.lossyScale.y, t.lossyScale.z }} }},
    }};
    sampledDict[relativePath] = tData;
}}

var sampledRootLocalPos = targetGo.transform.localPosition;
var rootMotionDelta = new float[] {{
    sampledRootLocalPos.x - restRootLocalPos.x,
    sampledRootLocalPos.y - restRootLocalPos.y,
    sampledRootLocalPos.z - restRootLocalPos.z
}};

// If restorePose is enabled, revert transforms back to their recorded pristine states
if (restorePose)
{{
    foreach (var t in transformsToSnapshot)
    {{
        if (t != null)
        {{
            t.localPosition = restPos[t];
            t.localRotation = restRot[t];
            t.localScale = restScale[t];
        }}
    }}
}}

return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "success", true }},
    {{ "clipName", clip.name }},
    {{ "clipPath", clipPath }},
    {{ "targetPath", targetPath }},
    {{ "sampleTime", sampleTime }},
    {{ "poseRestored", restorePose }},
    {{ "sampledTransforms", sampledDict }},
    {{ "rootMotionDelta", rootMotionDelta }},
}};
"""
