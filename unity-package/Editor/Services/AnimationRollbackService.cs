using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    internal sealed class AnimationRollbackEntry
    {
        public string clipPath;
        public AnimationClip clip;
        public string backupId;
        public string label;
    }

    internal static class AnimationRollbackService
    {
        public static void RevertUndoThenRestore(
            int undoGroup,
            IReadOnlyList<AnimationRollbackEntry> entries,
            List<string> warnings)
        {
            try
            {
                Undo.RevertAllDownToGroup(undoGroup);
            }
            catch (Exception ex)
            {
                warnings.Add($"Undo revert warning: {ex.Message}");
            }

            foreach (var entry in entries)
            {
                if (entry?.clip == null || string.IsNullOrEmpty(entry.clipPath) || string.IsNullOrEmpty(entry.backupId))
                {
                    continue;
                }

                var restore = AnimationBackupService.RestoreBackupForRollback(
                    entry.clip, entry.clipPath, entry.backupId);
                if (!restore.success)
                {
                    warnings.Add($"{entry.label ?? "Animation"} rollback warning: {restore.error}");
                }
            }

            try
            {
                AssetDatabase.SaveAssets();
            }
            catch (Exception ex)
            {
                warnings.Add($"Rollback save warning: {ex.Message}");
            }
        }
    }
}
