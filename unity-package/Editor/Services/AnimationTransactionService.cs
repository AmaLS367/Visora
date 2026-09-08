using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class AnimationTransactionOperation
    {
        public string operationType;
        public string clipPath;
        public string targetPath;
        public string typeName;
        public string propertyName;
        public float time;
        public float oldTime;
        public float newTime;
        public float startTime;
        public float duration;
        public float value;
        public float[] values;
        public string tangentMode;
        public string functionName;
        public int intParameter;
        public float floatParameter;
        public string stringParameter;
    }

    [Serializable]
    public class AnimationTransactionRequest
    {
        public string transactionId;
        public string description;
        public List<AnimationTransactionOperation> operations = new List<AnimationTransactionOperation>();
    }

    [Serializable]
    public class AnimationTransactionResult
    {
        public bool success = true;
        public string error;
        public string transactionId;
        public int appliedOperationsCount;
        public int keyframesModifiedCount;
        public bool rollbackPerformed;
        public List<string> backupIds = new List<string>();
        public List<string> affectedClips = new List<string>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Executes multi-clip, multi-operation animation edits atomically inside an Undo group.
    /// Creates pre-mutation backups of all touched clips before any modification.
    /// If any operation fails, rolls back all touched clips from their backup files and reverts the Undo group.
    /// </summary>
    public static class AnimationTransactionService
    {
        public static AnimationTransactionResult ExecuteTransaction(AnimationTransactionRequest request)
        {
            var result = new AnimationTransactionResult
            {
                transactionId = string.IsNullOrEmpty(request?.transactionId)
                    ? "tx_anim_" + Guid.NewGuid().ToString("N").Substring(0, 8)
                    : request.transactionId
            };

            if (EditorApplication.isPlaying)
            {
                result.success = false;
                result.error = "Animation transactions require Edit Mode; exit Play Mode before running.";
                return result;
            }

            if (request == null || request.operations == null || request.operations.Count == 0)
            {
                result.success = true;
                result.appliedOperationsCount = 0;
                return result;
            }

            // Collect distinct clip paths
            var distinctClipPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var op in request.operations)
            {
                if (!string.IsNullOrEmpty(op.clipPath))
                {
                    distinctClipPaths.Add(op.clipPath);
                }
            }

            // Validate and create backups for all affected clips before touching any asset
            var backupMap = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var resolvedClips = new Dictionary<string, AnimationClip>(StringComparer.OrdinalIgnoreCase);

            foreach (var cp in distinctClipPaths)
            {
                var clip = AnimationPreviewService.ResolveClip(cp);
                if (clip == null)
                {
                    result.success = false;
                    result.error = $"Transaction aborted: referenced AnimationClip '{cp}' could not be resolved.";
                    return result;
                }

                resolvedClips[cp] = clip;
                try
                {
                    string backupId = AnimationBackupService.WriteBackup(clip, cp, "transaction");
                    backupMap[cp] = backupId;
                    result.backupIds.Add(backupId);
                    result.affectedClips.Add(cp);
                }
                catch (Exception ex)
                {
                    result.success = false;
                    result.error = $"Transaction aborted: failed to create pre-mutation backup for '{cp}': {ex.Message}";
                    return result;
                }
            }

            // Open Undo group
            Undo.IncrementCurrentGroup();
            int undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName(string.IsNullOrEmpty(request.description)
                ? "Visora Animation Transaction " + result.transactionId
                : request.description);

            int applied = 0;
            int keysModified = 0;

            try
            {
                for (int i = 0; i < request.operations.Count; i++)
                {
                    var op = request.operations[i];
                    string opType = op.operationType?.ToLowerInvariant() ?? "";

                    switch (opType)
                    {
                        case "set_keyframe":
                            {
                                var r = AnimationAuthoringService.SetKeyframe(
                                    op.clipPath,
                                    op.targetPath,
                                    op.typeName,
                                    op.propertyName,
                                    op.time,
                                    op.values,
                                    op.tangentMode,
                                    null,
                                    null,
                                    null);

                                if (!r.success)
                                {
                                    throw new InvalidOperationException($"Operation #{i} (set_keyframe) failed: {r.error}");
                                }
                                keysModified += r.channelsAffected != null ? r.channelsAffected.Count : 1;
                                break;
                            }

                        case "move_keyframe":
                            {
                                var r = AnimationAuthoringService.MoveKeyframe(
                                    op.clipPath,
                                    op.targetPath,
                                    op.typeName,
                                    op.propertyName,
                                    op.oldTime,
                                    op.newTime,
                                    null);

                                if (!r.success)
                                {
                                    throw new InvalidOperationException($"Operation #{i} (move_keyframe) failed: {r.error}");
                                }
                                keysModified += r.channelsAffected != null ? r.channelsAffected.Count : 1;
                                break;
                            }

                        case "remove_keyframe":
                            {
                                var r = AnimationAuthoringService.RemoveKeyframe(
                                    op.clipPath,
                                    op.targetPath,
                                    op.typeName,
                                    op.propertyName,
                                    op.time,
                                    null);

                                if (!r.success)
                                {
                                    throw new InvalidOperationException($"Operation #{i} (remove_keyframe) failed: {r.error}");
                                }
                                keysModified += r.channelsAffected != null ? r.channelsAffected.Count : 1;
                                break;
                            }

                        case "set_keyframe_hold":
                            {
                                float[] holdVals = op.values ?? (op.value != 0f ? new float[] { op.value } : null);
                                var r = AnimationAuthoringService.SetKeyframeHold(
                                    op.clipPath,
                                    op.targetPath,
                                    op.typeName,
                                    op.propertyName,
                                    op.startTime,
                                    op.startTime + op.duration,
                                    holdVals,
                                    null);

                                if (!r.success)
                                {
                                    throw new InvalidOperationException($"Operation #{i} (set_keyframe_hold) failed: {r.error}");
                                }
                                keysModified += r.channelsAffected != null ? r.channelsAffected.Count : 1;
                                break;
                            }

                        case "create_event":
                            {
                                var r = AnimationAuthoringService.CreateEvent(
                                    op.clipPath,
                                    op.time,
                                    op.functionName,
                                    op.stringParameter,
                                    op.floatParameter,
                                    op.intParameter,
                                    null);

                                if (!r.success)
                                {
                                    throw new InvalidOperationException($"Operation #{i} (create_event) failed: {r.error}");
                                }
                                break;
                            }

                        case "remove_event":
                            {
                                var r = AnimationAuthoringService.RemoveEvent(
                                    op.clipPath,
                                    op.time,
                                    op.functionName,
                                    null);

                                if (!r.success)
                                {
                                    throw new InvalidOperationException($"Operation #{i} (remove_event) failed: {r.error}");
                                }
                                break;
                            }

                        case "ensure_continuity":
                            {
                                if (resolvedClips.TryGetValue(op.clipPath, out var clip))
                                {
                                    clip.EnsureQuaternionContinuity();
                                    EditorUtility.SetDirty(clip);
                                }
                                break;
                            }

                        default:
                            throw new NotSupportedException($"Unsupported transaction operation type: '{op.operationType}'");
                    }

                    applied++;
                }

                // If all operations completed successfully, collapse undo group and save assets
                Undo.CollapseUndoOperations(undoGroup);
                AssetDatabase.SaveAssets();

                result.success = true;
                result.appliedOperationsCount = applied;
                result.keyframesModifiedCount = keysModified;
                return result;
            }
            catch (Exception ex)
            {
                // Rollback! Restore all clips from pre-mutation backups and revert Undo group
                result.success = false;
                result.error = ex.Message;
                result.rollbackPerformed = true;

                foreach (var kvp in backupMap)
                {
                    string cp = kvp.Key;
                    string backupId = kvp.Value;
                    if (resolvedClips.TryGetValue(cp, out var clip))
                    {
                        try
                        {
                            var restoreRes = AnimationBackupService.RestoreBackup(clip, cp, backupId, null);
                            if (!restoreRes.success)
                            {
                                result.warnings.Add($"Rollback warning: could not restore '{cp}' from backup '{backupId}': {restoreRes.error}");
                            }
                        }
                        catch (Exception rex)
                        {
                            result.warnings.Add($"Rollback error restoring '{cp}': {rex.Message}");
                        }
                    }
                }

                try
                {
                    Undo.RevertAllDownToGroup(undoGroup);
                }
                catch (Exception uex)
                {
                    result.warnings.Add($"Undo revert warning: {uex.Message}");
                }

                return result;
            }
        }
    }
}
