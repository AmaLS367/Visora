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

        public static Type ResolveComponentType(string typeName)
        {
            if (string.IsNullOrEmpty(typeName))
            {
                throw new ArgumentException("typeName must not be empty.", nameof(typeName));
            }

            // Transform and GameObject are common cases; resolve without searching loaded assemblies.
            if (typeName == "Transform")
            {
                return typeof(Transform);
            }
            if (typeName == "GameObject")
            {
                return typeof(GameObject);
            }

            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                var candidate = assembly.GetType("UnityEngine." + typeName)
                    ?? assembly.GetType(typeName);
                if (candidate != null && (typeof(Component).IsAssignableFrom(candidate) || candidate == typeof(GameObject)))
                {
                    return candidate;
                }
            }

            throw new ArgumentException($"Could not resolve component type '{typeName}'.", nameof(typeName));
        }

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

        public static Dictionary<string, object> ToDictionary(AnimationClipEditResult r)
        {
            var dict = new Dictionary<string, object>
            {
                { "success", r.success }, { "clipPath", r.clipPath }, { "targetPath", r.targetPath },
                { "typeName", r.typeName }, { "propertyName", r.propertyName },
                { "channelsAffected", r.channelsAffected }, { "curveCreated", r.curveCreated },
                { "hasTime", r.hasTime }, { "hasPreviousTime", r.hasPreviousTime },
                { "keysCleared", r.keysCleared }, { "backupId", r.backupId }, { "undoGroupId", r.undoGroupId },
                { "warnings", r.warnings },
            };
            if (r.hasTime) dict["time"] = r.time;
            if (r.hasPreviousTime) dict["previousTime"] = r.previousTime;
            if (r.error != null) dict["error"] = r.error;
            return dict;
        }

        public static Dictionary<string, object> ToDictionary(ListAnimationKeyframesResult r)
        {
            var keyframes = new List<object>();
            foreach (var k in r.keyframes)
            {
                keyframes.Add(new Dictionary<string, object>
                {
                    { "time", k.time }, { "values", k.values }, { "exact", k.exact },
                    { "inTangents", k.inTangents }, { "outTangents", k.outTangents }, { "tangentMode", k.tangentMode },
                });
            }
            var dict = new Dictionary<string, object>
            {
                { "success", r.success }, { "clipPath", r.clipPath }, { "targetPath", r.targetPath },
                { "typeName", r.typeName }, { "propertyName", r.propertyName },
                { "channels", r.channels }, { "keyframes", keyframes },
            };
            if (r.error != null) dict["error"] = r.error;
            return dict;
        }

        private static AnimationClip LoadClipForWrite(string clipPath)
        {
            return AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
        }

        private static GameObject FindLiveInstance(string targetPath)
        {
            return string.IsNullOrEmpty(targetPath) ? null : GameObject.Find(targetPath);
        }

        private static float[] ExpandValue(float[] value, int channelCount, string paramName)
        {
            if (value == null || value.Length == 0)
            {
                throw new ArgumentException(
                    $"{paramName} must have exactly {channelCount} value(s) for this property, got {(value?.Length ?? 0)}.", paramName);
            }
            if (value.Length == 1 && channelCount > 1)
            {
                var expanded = new float[channelCount];
                for (int i = 0; i < channelCount; i++)
                {
                    expanded[i] = value[0];
                }
                return expanded;
            }
            if (value.Length != channelCount)
            {
                throw new ArgumentException(
                    $"{paramName} must have exactly {channelCount} value(s) for this property, got {value.Length}.", paramName);
            }
            return value;
        }

        private static int UpsertKey(AnimationCurve curve, float time, float value, string tangentMode, float clipFrameRate)
        {
            int existingIndex = FindKeyIndexNearTime(curve, time, clipFrameRate);
            if (existingIndex < 0)
            {
                int newIndex = curve.AddKey(new Keyframe(time, value));
                ApplyTangentMode(curve, newIndex, tangentMode ?? "smooth");
                return newIndex;
            }

            var key = curve[existingIndex];
            key.time = time;
            key.value = value;
            int keyIndex = curve.MoveKey(existingIndex, key);
            if (tangentMode != null)
            {
                ApplyTangentMode(curve, keyIndex, tangentMode);
            }
            return keyIndex;
        }

        public static AnimationClipEditResult SetKeyframe(
            string clipPath, string targetPath, string typeName, string propertyName,
            float time, float[] values, string tangentMode, float[] inTangent, float[] outTangent, string operationId)
        {
            if (AnimationBackupService.TryGetCached(operationId, out AnimationClipEditResult cached))
            {
                return cached;
            }

            var result = new AnimationClipEditResult
            {
                clipPath = clipPath,
                targetPath = targetPath,
                typeName = typeName,
                propertyName = propertyName,
            };

            string editModeError = AnimationBackupService.CheckEditMode();
            if (editModeError != null)
            {
                result.success = false;
                result.error = editModeError;
                return result;
            }

            var clip = LoadClipForWrite(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip not found at exact path '{clipPath}'.";
                return result;
            }

            Type componentType;
            string[] validModes = { "smooth", "linear", "step", "ease_in", "ease_out", "ease_in_out" };
            if (tangentMode != null && Array.IndexOf(validModes, tangentMode) < 0)
            {
                result.success = false;
                result.error = $"tangentMode '{tangentMode}' is not one of: {string.Join(", ", validModes)}.";
                return result;
            }
            try
            {
                componentType = ResolveComponentType(typeName);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            string[] channels;
            bool curveExisted;
            try
            {
                var liveInstance = FindLiveInstance(targetPath);
                channels = ResolveChannels(clip, targetPath, componentType, propertyName, liveInstance, out curveExisted);
                values = ExpandValue(values, channels.Length, nameof(values));
                if (inTangent != null) inTangent = ExpandValue(inTangent, channels.Length, nameof(inTangent));
                if (outTangent != null) outTangent = ExpandValue(outTangent, channels.Length, nameof(outTangent));
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            string backupId;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "set_animation_keyframe");
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Backup failed, edit aborted: {ex.Message}";
                return result;
            }

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora: set_animation_keyframe");

            try
            {
                for (int i = 0; i < channels.Length; i++)
                {
                    var binding = new EditorCurveBinding { path = targetPath, type = componentType, propertyName = channels[i] };
                    var curve = AnimationUtility.GetEditorCurve(clip, binding) ?? new AnimationCurve();

                    Undo.RecordObject(clip, "Visora: set_animation_keyframe");
                    int keyIndex = UpsertKey(curve, time, values[i], tangentMode, clip.frameRate);
                    if (inTangent != null) SetTangentValue(curve, keyIndex, left: true, value: inTangent[i]);
                    if (outTangent != null) SetTangentValue(curve, keyIndex, left: false, value: outTangent[i]);

                    AnimationUtility.SetEditorCurve(clip, binding, curve);
                }

                Undo.CollapseUndoOperations(undoGroup);

                result.success = true;
                result.channelsAffected.AddRange(channels);
                result.curveCreated = !curveExisted;
                result.time = time;
                result.hasTime = true;
                result.backupId = backupId;
                result.undoGroupId = undoGroup;
                AnimationBackupService.CacheSuccess(operationId, result);
            }
            catch (Exception ex)
            {
                Undo.RevertAllDownToGroup(undoGroup);
                result.success = false;
                result.error = ex.Message;
            }

            return result;
        }

        public static AnimationClipEditResult MoveKeyframe(
            string clipPath, string targetPath, string typeName, string propertyName,
            float fromTime, float toTime, string operationId)
        {
            if (AnimationBackupService.TryGetCached(operationId, out AnimationClipEditResult cached))
            {
                return cached;
            }

            var result = new AnimationClipEditResult
            {
                clipPath = clipPath,
                targetPath = targetPath,
                typeName = typeName,
                propertyName = propertyName,
            };

            string editModeError = AnimationBackupService.CheckEditMode();
            if (editModeError != null)
            {
                result.success = false;
                result.error = editModeError;
                return result;
            }

            var clip = LoadClipForWrite(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip not found at exact path '{clipPath}'.";
                return result;
            }

            Type componentType;
            try
            {
                componentType = ResolveComponentType(typeName);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            var liveInstance = FindLiveInstance(targetPath);
            string[] channels = ResolveChannels(clip, targetPath, componentType, propertyName, liveInstance, out _);

            var bindings = new EditorCurveBinding[channels.Length];
            var curves = new AnimationCurve[channels.Length];
            var fromIndices = new int[channels.Length];

            for (int i = 0; i < channels.Length; i++)
            {
                bindings[i] = new EditorCurveBinding { path = targetPath, type = componentType, propertyName = channels[i] };
                curves[i] = AnimationUtility.GetEditorCurve(clip, bindings[i]);
                if (curves[i] == null)
                {
                    result.success = false;
                    result.error = $"No curve found for '{channels[i]}'.";
                    return result;
                }

                int fromIdx = FindKeyIndexNearTime(curves[i], fromTime, clip.frameRate);
                if (fromIdx < 0)
                {
                    result.success = false;
                    result.error = $"No keyframe found near {fromTime:F4}s on channel '{channels[i]}'.";
                    return result;
                }
                fromIndices[i] = fromIdx;

                int toIdx = FindKeyIndexNearTime(curves[i], toTime, clip.frameRate);
                if (toIdx >= 0 && toIdx != fromIdx)
                {
                    result.success = false;
                    result.error = $"A keyframe already exists near {toTime:F4}s on channel '{channels[i]}'; move aborted to prevent overwrite.";
                    return result;
                }
            }

            string backupId;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "move_animation_keyframe");
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Backup failed, edit aborted: {ex.Message}";
                return result;
            }

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora: move_animation_keyframe");

            try
            {
                for (int i = 0; i < channels.Length; i++)
                {
                    Undo.RecordObject(clip, "Visora: move_animation_keyframe");
                    var key = curves[i][fromIndices[i]];
                    key.time = toTime;
                    curves[i].MoveKey(fromIndices[i], key);
                    AnimationUtility.SetEditorCurve(clip, bindings[i], curves[i]);
                }

                Undo.CollapseUndoOperations(undoGroup);

                result.success = true;
                result.channelsAffected.AddRange(channels);
                result.time = toTime;
                result.hasTime = true;
                result.previousTime = fromTime;
                result.hasPreviousTime = true;
                result.backupId = backupId;
                result.undoGroupId = undoGroup;
                AnimationBackupService.CacheSuccess(operationId, result);
            }
            catch (Exception ex)
            {
                Undo.RevertAllDownToGroup(undoGroup);
                result.success = false;
                result.error = ex.Message;
            }

            return result;
        }

        public static AnimationClipEditResult RemoveKeyframe(
            string clipPath, string targetPath, string typeName, string propertyName,
            float time, string operationId)
        {
            if (AnimationBackupService.TryGetCached(operationId, out AnimationClipEditResult cached))
            {
                return cached;
            }

            var result = new AnimationClipEditResult
            {
                clipPath = clipPath,
                targetPath = targetPath,
                typeName = typeName,
                propertyName = propertyName,
            };

            string editModeError = AnimationBackupService.CheckEditMode();
            if (editModeError != null)
            {
                result.success = false;
                result.error = editModeError;
                return result;
            }

            var clip = LoadClipForWrite(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip not found at exact path '{clipPath}'.";
                return result;
            }

            Type componentType;
            try
            {
                componentType = ResolveComponentType(typeName);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            var liveInstance = FindLiveInstance(targetPath);
            string[] channels = ResolveChannels(clip, targetPath, componentType, propertyName, liveInstance, out _);

            var bindings = new EditorCurveBinding[channels.Length];
            var curves = new AnimationCurve[channels.Length];
            var keyIndices = new int[channels.Length];

            for (int i = 0; i < channels.Length; i++)
            {
                bindings[i] = new EditorCurveBinding { path = targetPath, type = componentType, propertyName = channels[i] };
                curves[i] = AnimationUtility.GetEditorCurve(clip, bindings[i]);
                if (curves[i] == null)
                {
                    result.success = false;
                    result.error = $"No curve found for '{channels[i]}'.";
                    return result;
                }

                int keyIndex = FindKeyIndexNearTime(curves[i], time, clip.frameRate);
                if (keyIndex < 0)
                {
                    float nearestTime = float.MaxValue;
                    float minDiff = float.MaxValue;
                    for (int k = 0; k < curves[i].length; k++)
                    {
                        float diff = Mathf.Abs(curves[i][k].time - time);
                        if (diff < minDiff)
                        {
                            minDiff = diff;
                            nearestTime = curves[i][k].time;
                        }
                    }
                    result.success = false;
                    result.error = minDiff < float.MaxValue
                        ? $"No keyframe found near {time:F4}s on channel '{channels[i]}' (nearest is at {nearestTime:F4}s)."
                        : $"No keyframe found near {time:F4}s on channel '{channels[i]}'.";
                    return result;
                }
                keyIndices[i] = keyIndex;
            }

            string backupId;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "remove_animation_keyframe");
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Backup failed, edit aborted: {ex.Message}";
                return result;
            }

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora: remove_animation_keyframe");

            try
            {
                for (int i = 0; i < channels.Length; i++)
                {
                    Undo.RecordObject(clip, "Visora: remove_animation_keyframe");
                    curves[i].RemoveKey(keyIndices[i]);
                    AnimationUtility.SetEditorCurve(clip, bindings[i], curves[i]);
                }

                Undo.CollapseUndoOperations(undoGroup);

                result.success = true;
                result.channelsAffected.AddRange(channels);
                result.backupId = backupId;
                result.undoGroupId = undoGroup;
                AnimationBackupService.CacheSuccess(operationId, result);
            }
            catch (Exception ex)
            {
                Undo.RevertAllDownToGroup(undoGroup);
                result.success = false;
                result.error = ex.Message;
            }

            return result;
        }

        public static ListAnimationKeyframesResult ListKeyframes(
            string clipPath, string targetPath, string typeName, string propertyName)
        {
            var result = new ListAnimationKeyframesResult
            {
                clipPath = clipPath,
                targetPath = targetPath,
                typeName = typeName,
                propertyName = propertyName,
            };

            var clip = LoadClipForWrite(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip not found at exact path '{clipPath}'.";
                return result;
            }

            Type componentType;
            try
            {
                componentType = ResolveComponentType(typeName);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            var liveInstance = FindLiveInstance(targetPath);
            string[] channels = ResolveChannels(clip, targetPath, componentType, propertyName, liveInstance, out bool curveExisted);
            result.channels.AddRange(channels);

            if (!curveExisted)
            {
                result.success = true;
                return result;
            }

            float tolerance = Mathf.Max(0.5f / Mathf.Max(clip.frameRate, 1f), 0.0001f);
            var curves = new AnimationCurve[channels.Length];
            var rawTimes = new List<float>();

            for (int i = 0; i < channels.Length; i++)
            {
                var binding = new EditorCurveBinding { path = targetPath, type = componentType, propertyName = channels[i] };
                curves[i] = AnimationUtility.GetEditorCurve(clip, binding) ?? new AnimationCurve();
                for (int k = 0; k < curves[i].length; k++)
                {
                    rawTimes.Add(curves[i][k].time);
                }
            }

            rawTimes.Sort();
            var unionedTimes = new List<float>();
            foreach (float t in rawTimes)
            {
                if (unionedTimes.Count == 0 || Mathf.Abs(unionedTimes[unionedTimes.Count - 1] - t) > tolerance)
                {
                    unionedTimes.Add(t);
                }
            }

            foreach (float t in unionedTimes)
            {
                var vals = new float[channels.Length];
                var exact = new bool[channels.Length];
                var inT = new float[channels.Length];
                var outT = new float[channels.Length];
                var leftModes = new AnimationUtility.TangentMode[channels.Length];
                var rightModes = new AnimationUtility.TangentMode[channels.Length];

                for (int c = 0; c < channels.Length; c++)
                {
                    int foundIdx = FindKeyIndexNearTime(curves[c], t, clip.frameRate);

                    if (foundIdx >= 0)
                    {
                        exact[c] = true;
                        var kf = curves[c][foundIdx];
                        vals[c] = kf.value;
                        inT[c] = kf.inTangent;
                        outT[c] = kf.outTangent;
                        leftModes[c] = AnimationUtility.GetKeyLeftTangentMode(curves[c], foundIdx);
                        rightModes[c] = AnimationUtility.GetKeyRightTangentMode(curves[c], foundIdx);
                    }
                    else
                    {
                        exact[c] = false;
                        vals[c] = curves[c].Evaluate(t);
                        inT[c] = 0f;
                        outT[c] = 0f;
                    }
                }

                string tangentMode;
                if (exact.All(e => !e))
                {
                    tangentMode = "n/a";
                }
                else if (!exact.All(e => e))
                {
                    tangentMode = "custom";
                }
                else
                {
                    bool allClamped = leftModes.All(m => m == AnimationUtility.TangentMode.ClampedAuto)
                        && rightModes.All(m => m == AnimationUtility.TangentMode.ClampedAuto);
                    bool allLinear = leftModes.All(m => m == AnimationUtility.TangentMode.Linear)
                        && rightModes.All(m => m == AnimationUtility.TangentMode.Linear);
                    bool allStep = rightModes.All(m => m == AnimationUtility.TangentMode.Constant);

                    if (allClamped) tangentMode = "smooth";
                    else if (allLinear) tangentMode = "linear";
                    else if (allStep) tangentMode = "step";
                    else tangentMode = "custom";
                }

                result.keyframes.Add(new AnimationKeyframeInfo
                {
                    time = t,
                    values = vals,
                    exact = exact,
                    inTangents = inT,
                    outTangents = outT,
                    tangentMode = tangentMode,
                });
            }

            result.success = true;
            return result;
        }

        private static int SetHoldBoundary(AnimationCurve curve, float t, float value, float clipFrameRate, bool setStepRightTangent)
        {
            int existing = FindKeyIndexNearTime(curve, t, clipFrameRate);
            int index = existing >= 0
                ? curve.MoveKey(existing, new Keyframe(t, value))
                : curve.AddKey(new Keyframe(t, value));
            if (setStepRightTangent)
            {
                ApplyTangentMode(curve, index, "step");
            }
            else if (existing < 0)
            {
                ApplyTangentMode(curve, index, "smooth");
            }
            return index;
        }

        public static AnimationClipEditResult SetKeyframeHold(
            string clipPath, string targetPath, string typeName, string propertyName,
            float time, float holdUntil, float[] value, string operationId)
        {
            if (AnimationBackupService.TryGetCached(operationId, out AnimationClipEditResult cached))
            {
                return cached;
            }

            var result = new AnimationClipEditResult
            {
                clipPath = clipPath,
                targetPath = targetPath,
                typeName = typeName,
                propertyName = propertyName,
            };

            string editModeError = AnimationBackupService.CheckEditMode();
            if (editModeError != null)
            {
                result.success = false;
                result.error = editModeError;
                return result;
            }

            if (holdUntil <= time)
            {
                result.success = false;
                result.error = $"holdUntil ({holdUntil}) must be strictly greater than time ({time}).";
                return result;
            }

            var clip = LoadClipForWrite(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip not found at exact path '{clipPath}'.";
                return result;
            }

            Type componentType;
            try
            {
                componentType = ResolveComponentType(typeName);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            var liveInstance = FindLiveInstance(targetPath);
            string[] channels = ResolveChannels(clip, targetPath, componentType, propertyName, liveInstance, out bool curveExisted);
            if (value != null)
            {
                value = ExpandValue(value, channels.Length, nameof(value));
            }

            string backupId;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "set_keyframe_hold");
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Backup failed, edit aborted: {ex.Message}";
                return result;
            }

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora: set_keyframe_hold");

            try
            {
                var clearedTimes = new SortedSet<float>();

                for (int i = 0; i < channels.Length; i++)
                {
                    var binding = new EditorCurveBinding { path = targetPath, type = componentType, propertyName = channels[i] };
                    var curve = AnimationUtility.GetEditorCurve(clip, binding) ?? new AnimationCurve();

                    Undo.RecordObject(clip, "Visora: set_keyframe_hold");

                    float holdVal = value != null ? value[i] : curve.Evaluate(time);

                    // Clear keys strictly between time and holdUntil
                    for (int k = curve.length - 1; k >= 0; k--)
                    {
                        float kt = curve[k].time;
                        if (kt > time && kt < holdUntil)
                        {
                            clearedTimes.Add(kt);
                            curve.RemoveKey(k);
                        }
                    }

                    SetHoldBoundary(curve, time, holdVal, clip.frameRate, setStepRightTangent: true);
                    SetHoldBoundary(curve, holdUntil, holdVal, clip.frameRate, setStepRightTangent: false);

                    AnimationUtility.SetEditorCurve(clip, binding, curve);
                }

                Undo.CollapseUndoOperations(undoGroup);

                result.success = true;
                result.channelsAffected.AddRange(channels);
                result.curveCreated = !curveExisted;
                result.time = time;
                result.hasTime = true;
                result.keysCleared.AddRange(clearedTimes);
                result.backupId = backupId;
                result.undoGroupId = undoGroup;
                AnimationBackupService.CacheSuccess(operationId, result);
            }
            catch (Exception ex)
            {
                Undo.RevertAllDownToGroup(undoGroup);
                result.success = false;
                result.error = ex.Message;
            }

            return result;
        }

        public static Dictionary<string, object> ToDictionary(AnimationEventEditResult r)
        {
            var dict = new Dictionary<string, object>
            {
                { "success", r.success },
                { "clipPath", r.clipPath },
                { "hasTime", r.hasTime },
                { "functionName", r.functionName },
                { "eventsAffected", r.eventsAffected },
                { "backupId", r.backupId },
                { "undoGroupId", r.undoGroupId },
                { "warnings", r.warnings },
            };
            if (r.hasTime) dict["time"] = r.time;
            if (r.error != null) dict["error"] = r.error;
            return dict;
        }

        public static AnimationEventEditResult CreateEvent(
            string clipPath, float time, string functionName, string stringParam, float floatParam, int intParam, string operationId)
        {
            if (AnimationBackupService.TryGetCached(operationId, out AnimationEventEditResult cached))
            {
                return cached;
            }

            var result = new AnimationEventEditResult
            {
                clipPath = clipPath,
                time = time,
                hasTime = true,
                functionName = functionName,
            };

            string editModeError = AnimationBackupService.CheckEditMode();
            if (editModeError != null)
            {
                result.success = false;
                result.error = editModeError;
                return result;
            }

            var clip = LoadClipForWrite(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip not found at exact path '{clipPath}'.";
                return result;
            }

            string backupId;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "create_animation_event");
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Backup failed, edit aborted: {ex.Message}";
                return result;
            }

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora: create_animation_event");

            try
            {
                Undo.RecordObject(clip, "Visora: create_animation_event");
                var events = AnimationUtility.GetAnimationEvents(clip).ToList();

                bool duplicate = events.Any(e => Mathf.Approximately(e.time, time) && e.functionName == functionName
                    && e.stringParameter == stringParam && Mathf.Approximately(e.floatParameter, floatParam) && e.intParameter == intParam);
                if (duplicate)
                {
                    result.warnings.Add(string.Format(System.Globalization.CultureInfo.InvariantCulture, "An identical event already exists at {0:F4}s; added anyway.", time));
                }

                events.Add(new AnimationEvent
                {
                    time = time,
                    functionName = functionName,
                    stringParameter = stringParam,
                    floatParameter = floatParam,
                    intParameter = intParam,
                });
                events.Sort((a, b) => a.time.CompareTo(b.time));
                AnimationUtility.SetAnimationEvents(clip, events.ToArray());

                Undo.CollapseUndoOperations(undoGroup);

                result.success = true;
                result.eventsAffected = 1;
                result.backupId = backupId;
                result.undoGroupId = undoGroup;
                AnimationBackupService.CacheSuccess(operationId, result);
            }
            catch (Exception ex)
            {
                Undo.RevertAllDownToGroup(undoGroup);
                result.success = false;
                result.error = ex.Message;
            }

            return result;
        }

        public static AnimationEventEditResult RemoveEvent(string clipPath, float time, string functionName, string operationId)
        {
            if (AnimationBackupService.TryGetCached(operationId, out AnimationEventEditResult cached))
            {
                return cached;
            }

            var result = new AnimationEventEditResult
            {
                clipPath = clipPath,
                time = time,
                hasTime = true,
                functionName = functionName,
            };

            string editModeError = AnimationBackupService.CheckEditMode();
            if (editModeError != null)
            {
                result.success = false;
                result.error = editModeError;
                return result;
            }

            var clip = LoadClipForWrite(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip not found at exact path '{clipPath}'.";
                return result;
            }

            var events = AnimationUtility.GetAnimationEvents(clip);
            float tolerance = Mathf.Max(0.5f / Mathf.Max(clip.frameRate, 1f), 0.0001f);
            var toRemove = events.Where(e => Mathf.Abs(e.time - time) <= tolerance
                && (string.IsNullOrEmpty(functionName) || e.functionName == functionName)).ToList();

            if (toRemove.Count == 0)
            {
                result.success = false;
                result.error = string.Format(
                    System.Globalization.CultureInfo.InvariantCulture,
                    "No animation event found near {0:F4}s{1}.",
                    time,
                    !string.IsNullOrEmpty(functionName) ? $" named '{functionName}'" : "");
                return result;
            }

            string backupId;
            try
            {
                backupId = AnimationBackupService.WriteBackup(clip, clipPath, "remove_animation_event");
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Backup failed, edit aborted: {ex.Message}";
                return result;
            }

            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Visora: remove_animation_event");

            try
            {
                Undo.RecordObject(clip, "Visora: remove_animation_event");
                var remaining = events.Except(toRemove).ToArray();
                AnimationUtility.SetAnimationEvents(clip, remaining);

                Undo.CollapseUndoOperations(undoGroup);

                result.success = true;
                result.eventsAffected = toRemove.Count;
                result.backupId = backupId;
                result.undoGroupId = undoGroup;
                AnimationBackupService.CacheSuccess(operationId, result);
            }
            catch (Exception ex)
            {
                Undo.RevertAllDownToGroup(undoGroup);
                result.success = false;
                result.error = ex.Message;
            }

            return result;
        }
    }

    [Serializable]
    public class AnimationKeyframeInfo
    {
        public float time;
        public float[] values;
        public bool[] exact;
        public float[] inTangents;
        public float[] outTangents;
        public string tangentMode;
    }

    [Serializable]
    public class ListAnimationKeyframesResult
    {
        public bool success;
        public string error;
        public string clipPath;
        public string targetPath;
        public string typeName;
        public string propertyName;
        public List<string> channels = new List<string>();
        public List<AnimationKeyframeInfo> keyframes = new List<AnimationKeyframeInfo>();
    }

    [Serializable]
    public class AnimationClipEditResult
    {
        public bool success;
        public string error;
        public string clipPath;
        public string targetPath;
        public string typeName;
        public string propertyName;
        public List<string> channelsAffected = new List<string>();
        public bool curveCreated;
        public float time;
        public bool hasTime;
        public float previousTime;
        public bool hasPreviousTime;
        public List<float> keysCleared = new List<float>();
        public string backupId;
        public int undoGroupId;
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class AnimationEventEditResult
    {
        public bool success;
        public string error;
        public string clipPath;
        public float time;
        public bool hasTime;
        public string functionName;
        public int eventsAffected;
        public string backupId;
        public int undoGroupId;
        public List<string> warnings = new List<string>();
    }
}


