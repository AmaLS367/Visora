using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    /// <summary>
    /// Typed, safe operations to create and edit AnimationClip curves and events.
    /// Every mutating method here wraps its Unity-side change in one Undo group and one
    /// AnimationBackupService.WriteBackup call before writing, so one MCP call is always
    /// one atomic, undoable, backed-up edit — never a sequence of independently-committed steps.
    /// </summary>
    public static class AnimationAuthoringService
    {
        // A newly-authored curve with no prior binding defaults to this shape. Rotation defaults
        // to Euler, not quaternion, because that is what authoring a rotation key through Unity's
        // own Animation window produces, and it is far easier for an agent to reason about three
        // Euler channels than a four-component quaternion.
        private static readonly Dictionary<string, string[]> WellKnownVectorProperties = new Dictionary<string, string[]>
        {
            ["m_LocalPosition"] = new[] { "x", "y", "z" },
            ["m_LocalScale"] = new[] { "x", "y", "z" },
            ["localEulerAnglesRaw"] = new[] { "x", "y", "z" },
        };

        // SHARED-ALGORITHM:ResolveComponentType START
        public static Type ResolveComponentType(string typeName)
        {
            if (string.IsNullOrEmpty(typeName))
            {
                throw new ArgumentException("typeName must not be empty.", nameof(typeName));
            }

            // Transform is overwhelmingly the common case and resolving it by name through every
            // loaded assembly on each call would be wasteful.
            if (typeName == "Transform")
            {
                return typeof(Transform);
            }

            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                var candidate = assembly.GetType("UnityEngine." + typeName)
                    ?? assembly.GetType(typeName);
                if (candidate != null && typeof(Component).IsAssignableFrom(candidate))
                {
                    return candidate;
                }
            }

            throw new ArgumentException($"Could not resolve component type '{typeName}'.", nameof(typeName));
        }
        // SHARED-ALGORITHM:ResolveComponentType END

        // Canonical component order, never alphabetical: alphabetical sort puts ".w" before ".x"
        // on an existing quaternion curve, which would silently transpose every value passed in
        // by a caller that (reasonably) assumes x/y/z/w order. Two vocabularies exist side by
        // side — Vector/Quaternion channels are x/y/z/w, Color channels are r/g/b/a (confirmed:
        // Unity animates Color via .r/.g/.b/.a bindings, never .x/.y/.z/.w) — so ordering checks
        // whichever vocabulary the actual suffixes use rather than assuming one.
        private static readonly string[] VectorChannelOrder = { "x", "y", "z", "w" };
        private static readonly string[] ColorChannelOrder = { "r", "g", "b", "a" };

        private static string[] OrderByCanonicalSuffix(IEnumerable<string> propertyNames, string propertyName)
        {
            var names = propertyNames.ToArray();
            bool isColor = names.Any(name =>
            {
                string s = name.Length > propertyName.Length ? name.Substring(propertyName.Length + 1) : "";
                return Array.IndexOf(ColorChannelOrder, s) >= 0;
            });
            string[] order = isColor ? ColorChannelOrder : VectorChannelOrder;

            return names
                .OrderBy(name =>
                {
                    string suffix = name.Length > propertyName.Length ? name.Substring(propertyName.Length + 1) : "";
                    int index = Array.IndexOf(order, suffix);
                    return index >= 0 ? index : int.MaxValue;
                })
                .ToArray();
        }

        // SHARED-ALGORITHM:ResolveChannels START
        // Given a logical property (e.g. "m_LocalPosition"), returns the concrete curve binding
        // names already used by the clip if the curve exists, or a shape inferred from a built-in
        // table / SerializedObject introspection if it does not. Never mixes representations: an
        // existing quaternion rotation curve is returned as its 4 channels as-is, never silently
        // converted to Euler.
        public static string[] ResolveChannels(
            AnimationClip clip,
            string targetPath,
            Type componentType,
            string propertyName,
            GameObject liveInstance,
            out bool curveExisted)
        {
            var existing = AnimationUtility.GetCurveBindings(clip)
                .Where(b => b.path == targetPath
                    && b.type == componentType
                    && (b.propertyName == propertyName || b.propertyName.StartsWith(propertyName + ".", StringComparison.Ordinal)))
                .Select(b => b.propertyName);

            var orderedExisting = OrderByCanonicalSuffix(existing, propertyName);
            if (orderedExisting.Length > 0)
            {
                curveExisted = true;
                return orderedExisting;
            }

            curveExisted = false;

            if (WellKnownVectorProperties.TryGetValue(propertyName, out var suffixes))
            {
                return suffixes.Select(suffix => $"{propertyName}.{suffix}").ToArray();
            }

            // Unity's animation system binds to *serialized* field names (e.g. Light's animatable
            // "m_Intensity"), which routinely differ from the public C# property a script would
            // use ("intensity"). Reflecting on the public API silently fails to find the real
            // binding at all — SerializedObject is the only thing that speaks the same vocabulary
            // AnimationUtility does. This requires a live instance of componentType somewhere in
            // the open scene; there is no way to ask "what shape would this serialized property
            // have" without one.
            var component = liveInstance != null ? liveInstance.GetComponent(componentType) : null;
            if (component == null)
            {
                throw new ArgumentException(
                    $"Property '{propertyName}' is not in the well-known table and no live '{componentType.Name}' "
                    + $"was found at '{targetPath}' in the open scene to inspect its serialized shape.");
            }

            using var serialized = new SerializedObject(component);
            var property = serialized.FindProperty(propertyName);
            if (property == null)
            {
                throw new ArgumentException(
                    $"Serialized property '{propertyName}' not found on '{componentType.Name}' at '{targetPath}'.");
            }

            return property.propertyType switch
            {
                SerializedPropertyType.Vector2 => new[] { $"{propertyName}.x", $"{propertyName}.y" },
                SerializedPropertyType.Vector3 => new[] { $"{propertyName}.x", $"{propertyName}.y", $"{propertyName}.z" },
                SerializedPropertyType.Vector4 or SerializedPropertyType.Quaternion
                    => new[] { $"{propertyName}.x", $"{propertyName}.y", $"{propertyName}.z", $"{propertyName}.w" },
                SerializedPropertyType.Color
                    => new[] { $"{propertyName}.r", $"{propertyName}.g", $"{propertyName}.b", $"{propertyName}.a" },
                SerializedPropertyType.Float or SerializedPropertyType.Integer or SerializedPropertyType.Boolean
                    => new[] { propertyName },
                _ => throw new ArgumentException(
                    $"Serialized property '{propertyName}' has unsupported type '{property.propertyType}' for curve authoring."),
            };
        }
        // SHARED-ALGORITHM:ResolveChannels END

        // SHARED-ALGORITHM:MapTangentMode START
        // Maps the curated agent-facing vocabulary onto Unity's tangent presets. "step" is also
        // what set_keyframe_hold uses internally: a hold is two step-tangent keys, not a separate
        // tangent concept.
        public static void ApplyTangentMode(AnimationCurve curve, int keyIndex, string mode)
        {
            switch (mode)
            {
                case "linear":
                    AnimationUtility.SetKeyLeftTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Linear);
                    AnimationUtility.SetKeyRightTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Linear);
                    break;
                case "step":
                    AnimationUtility.SetKeyRightTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Constant);
                    break;
                case "ease_in":
                    AnimationUtility.SetKeyLeftTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Free);
                    SetTangentValue(curve, keyIndex, left: true, value: 0f);
                    AnimationUtility.SetKeyRightTangentMode(curve, keyIndex, AnimationUtility.TangentMode.ClampedAuto);
                    break;
                case "ease_out":
                    AnimationUtility.SetKeyLeftTangentMode(curve, keyIndex, AnimationUtility.TangentMode.ClampedAuto);
                    AnimationUtility.SetKeyRightTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Free);
                    SetTangentValue(curve, keyIndex, left: false, value: 0f);
                    break;
                case "ease_in_out":
                    AnimationUtility.SetKeyLeftTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Free);
                    AnimationUtility.SetKeyRightTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Free);
                    SetTangentValue(curve, keyIndex, left: true, value: 0f);
                    SetTangentValue(curve, keyIndex, left: false, value: 0f);
                    break;
                case "smooth":
                default:
                    AnimationUtility.SetKeyLeftTangentMode(curve, keyIndex, AnimationUtility.TangentMode.ClampedAuto);
                    AnimationUtility.SetKeyRightTangentMode(curve, keyIndex, AnimationUtility.TangentMode.ClampedAuto);
                    break;
            }
        }

        // Switches the given side to Free before writing the raw slope: leaving the mode at
        // whatever ApplyTangentMode set (e.g. ClampedAuto) means Unity still considers that side
        // auto-managed, and can silently recompute — discarding — the value just written the next
        // time the curve is touched. An explicit slope always means "manual," which is exactly
        // what Free mode records.
        private static void SetTangentValue(AnimationCurve curve, int keyIndex, bool left, float value)
        {
            if (left)
            {
                AnimationUtility.SetKeyLeftTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Free);
            }
            else
            {
                AnimationUtility.SetKeyRightTangentMode(curve, keyIndex, AnimationUtility.TangentMode.Free);
            }

            var key = curve[keyIndex];
            if (left)
            {
                key.inTangent = value;
            }
            else
            {
                key.outTangent = value;
            }
            curve.MoveKey(keyIndex, key);
        }
        // SHARED-ALGORITHM:MapTangentMode END

        // SHARED-ALGORITHM:FindKeyIndexNearTime START
        // Half a frame of tolerance, floored so a degenerate (zero or negative) frame rate cannot
        // divide by zero. Returns -1 rather than the closest key unconditionally: a caller outside
        // tolerance gets a clear "no key here" error instead of silently editing the wrong frame.
        public static int FindKeyIndexNearTime(AnimationCurve curve, float time, float clipFrameRate)
        {
            float tolerance = Mathf.Max(0.5f / Mathf.Max(clipFrameRate, 1f), 0.0001f);
            int bestIndex = -1;
            float bestDistance = float.MaxValue;

            for (int i = 0; i < curve.length; i++)
            {
                float distance = Mathf.Abs(curve[i].time - time);
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    bestIndex = i;
                }
            }

            return bestDistance <= tolerance ? bestIndex : -1;
        }
        // SHARED-ALGORITHM:FindKeyIndexNearTime END
    }
}
