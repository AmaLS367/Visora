using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class ClipBindingInfo
    {
        public string path;
        public string propertyName;
        public string type;
        public bool isDangerousCurve;
        public float minValue;
        public float maxValue;
    }

    [Serializable]
    public class AnimationInspectionResult
    {
        public bool success;
        public string error;
        public string clipName;
        public float length;
        public float frameRate;
        public bool isLooping;
        public int totalBindings;
        public List<ClipBindingInfo> bindings = new List<ClipBindingInfo>();
        public List<string> dangerousCurves = new List<string>();
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class SampledTransformInfo
    {
        public string name;
        public float[] position;
        public float[] rotationEuler;
        public float[] scale;
    }

    [Serializable]
    public class AnimationSampleResult
    {
        public bool success;
        public string error;
        public string clipName;
        public float sampleTime;
        public List<SampledTransformInfo> sampledTransforms = new List<SampledTransformInfo>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Introspects AnimationClips, curves, bindings, and performs non-destructive sampling.
    /// </summary>
    public static class AnimationInspectionService
    {
        public static AnimationClip FindClip(string clipName)
        {
            if (string.IsNullOrEmpty(clipName)) return null;

            var guids = AssetDatabase.FindAssets($"{clipName} t:AnimationClip");
            foreach (var guid in guids)
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
                if (clip != null && clip.name.Equals(clipName, StringComparison.OrdinalIgnoreCase))
                {
                    return clip;
                }
            }
            return null;
        }

        public static AnimationInspectionResult InspectClip(string clipName)
        {
            var result = new AnimationInspectionResult { clipName = clipName };
            var clip = FindClip(clipName);

            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip '{clipName}' not found in project assets.";
                return result;
            }

            result.length = clip.length;
            result.frameRate = clip.frameRate;
            result.isLooping = clip.isLooping;

            var bindings = AnimationUtility.GetCurveBindings(clip);
            result.totalBindings = bindings.Length;

            foreach (var b in bindings)
            {
                var curve = AnimationUtility.GetEditorCurve(clip, b);
                float minVal = float.MaxValue;
                float maxVal = float.MinValue;

                if (curve != null && curve.keys.Length > 0)
                {
                    foreach (var k in curve.keys)
                    {
                        if (k.value < minVal) minVal = k.value;
                        if (k.value > maxVal) maxVal = k.value;
                    }
                }
                else
                {
                    minVal = 0;
                    maxVal = 0;
                }

                bool isDangerous = b.propertyName.StartsWith("m_LocalPosition") || b.propertyName.StartsWith("m_LocalScale");
                if (isDangerous)
                {
                    result.dangerousCurves.Add($"{b.path}/{b.propertyName}");
                }

                result.bindings.Add(new ClipBindingInfo
                {
                    path = b.path,
                    propertyName = b.propertyName,
                    type = b.type != null ? b.type.Name : "",
                    isDangerousCurve = isDangerous,
                    minValue = minVal,
                    maxValue = maxVal
                });
            }

            result.success = true;
            return result;
        }

        public static AnimationSampleResult SampleClip(string clipName, string targetObjectName, float sampleTime)
        {
            var result = new AnimationSampleResult
            {
                clipName = clipName,
                sampleTime = sampleTime
            };

            var clip = FindClip(clipName);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip '{clipName}' not found.";
                return result;
            }

            var target = GameObject.Find(targetObjectName);
            if (target == null)
            {
                result.success = false;
                result.error = $"Target GameObject '{targetObjectName}' not found in active scene.";
                return result;
            }

            try
            {
                clip.SampleAnimation(target, sampleTime);

                var transforms = target.GetComponentsInChildren<Transform>(true);
                foreach (var t in transforms)
                {
                    var p = t.localPosition;
                    var r = t.localEulerAngles;
                    var s = t.localScale;

                    result.sampledTransforms.Add(new SampledTransformInfo
                    {
                        name = t.name,
                        position = new float[] { p.x, p.y, p.z },
                        rotationEuler = new float[] { r.x, r.y, r.z },
                        scale = new float[] { s.x, s.y, s.z }
                    });
                }

                result.success = true;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Failed to sample animation: {ex.Message}";
            }

            return result;
        }
    }
}
