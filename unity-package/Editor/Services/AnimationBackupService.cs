using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class AnimationBackupInfo
    {
        public string backupId;
        public string clipPath;
        public string createdAt;
        public string operation;
        public long sizeBytes;
    }

    [Serializable]
    public class ListAnimationBackupsResult
    {
        public bool success;
        public string error;
        public string clipPath;
        public List<AnimationBackupInfo> backups = new List<AnimationBackupInfo>();
    }

    [Serializable]
    public class RestoreAnimationClipResult
    {
        public bool success;
        public string error;
        public string clipPath;
        public string restoredFromBackupId;
        public string preRestoreBackupId;
        public List<string> warnings = new List<string>();
    }

    // Called by the legacy path's generated snippets (see AnimationAuthoringService's identical
    // ToDictionary methods) so backup list/restore also call this compiled service directly
    // instead of duplicating file I/O in a generated string.
    public static class AnimationBackupServiceDictionaries
    {
        public static Dictionary<string, object> ToDictionary(ListAnimationBackupsResult r)
        {
            var backups = new List<object>();
            foreach (var b in r.backups)
            {
                backups.Add(new Dictionary<string, object>
                {
                    { "backupId", b.backupId }, { "clipPath", b.clipPath },
                    { "createdAt", b.createdAt }, { "operation", b.operation }, { "sizeBytes", b.sizeBytes },
                });
            }
            var dict = new Dictionary<string, object> { { "success", r.success }, { "clipPath", r.clipPath }, { "backups", backups } };
            if (r.error != null) dict["error"] = r.error;
            return dict;
        }

        public static Dictionary<string, object> ToDictionary(RestoreAnimationClipResult r)
        {
            var dict = new Dictionary<string, object>
            {
                { "success", r.success }, { "clipPath", r.clipPath },
                { "restoredFromBackupId", r.restoredFromBackupId }, { "preRestoreBackupId", r.preRestoreBackupId },
                { "warnings", r.warnings },
            };
            if (r.error != null) dict["error"] = r.error;
            return dict;
        }
    }

    /// <summary>
    /// Writes, lists, and restores full-file backups of AnimationClip assets under
    /// VisoraBackups/ (a project-root sibling of Assets/ and Library/, never inside either).
    /// Has no knowledge of curves or events — every mutating operation in
    /// AnimationAuthoringService calls WriteBackup before touching a clip.
    /// </summary>
    public static class AnimationBackupService
    {
        private const string BackupRootFolderName = "VisoraBackups";

        private static string ProjectRoot => Directory.GetParent(Application.dataPath).FullName;

        private static string BackupRootPath => Path.Combine(ProjectRoot, BackupRootFolderName);

        // Resolves clipPath to a canonical absolute path and throws unless it is strictly inside
        // the project — rejects ".." and absolute paths, which is what actually matters against
        // an accidental or malformed clipPath. Path.GetFullPath is lexical only: it does not
        // resolve symlinks, so it is not a hardened defense against a symlink deliberately placed
        // inside the project by a local actor who already has write access to it — that attacker
        // already has far more direct ways to cause damage, and is out of scope for an Editor-side
        // tool operating on a project the same user controls. Every entry point that touches a
        // clip or a backup path goes through one of these two guards first.
        // Small helpers every mutating method needs, grouped into one region so every legacy
        // snippet splices them as one block rather than four separate lookups.
        // SHARED-ALGORITHM:PathAndModeGuards START
        private static string ResolveProjectPath(string relativePath, string paramName)
        {
            string projectRoot = Path.GetFullPath(ProjectRoot) + Path.DirectorySeparatorChar;
            string resolved = Path.GetFullPath(Path.Combine(ProjectRoot, relativePath ?? string.Empty));
            if (!resolved.StartsWith(projectRoot, StringComparison.Ordinal))
            {
                throw new ArgumentException($"{paramName} '{relativePath}' resolves outside the project.");
            }
            return resolved;
        }

        // Checked on the Unity main thread immediately before WriteBackup and the edit, by every
        // mutating method in this file and in AnimationAuthoringService (Tasks 4-5) — not only
        // once in Python before the HTTP call. A Python-side check is a fast-fail convenience;
        // Play Mode can start in the gap between that check and the request arriving, and a
        // caller invoking the native route directly bypasses the Python check entirely. Lives
        // here (Task 2) rather than in AnimationAuthoringService (Task 3+) purely so both classes
        // can reference it regardless of which one Unity compiles or the plan executes first.
        public static string CheckEditMode()
        {
            return EditorApplication.isPlaying
                ? "Clip authoring requires Edit Mode; exit Play Mode before editing this clip."
                : null;
        }

        private static string ResolveBackupPath(string backupId)
        {
            string backupRoot = Path.GetFullPath(BackupRootPath) + Path.DirectorySeparatorChar;
            string resolved = Path.GetFullPath(Path.Combine(BackupRootPath, backupId ?? string.Empty));
            if (!resolved.StartsWith(backupRoot, StringComparison.Ordinal))
            {
                throw new ArgumentException($"backupId '{backupId}' resolves outside VisoraBackups/.");
            }
            return resolved;
        }

        // Rejects a clipPath that isn't itself a standalone, importable .anim file — an
        // AnimationClip embedded as a sub-asset of an imported FBX is still a valid
        // AssetDatabase.LoadAssetAtPath<AnimationClip> result, but its "file" is the FBX, not a
        // .anim Visora can copy/replace independently; WriteBackup/RestoreBackup's whole approach
        // assumes the on-disk file *is* the clip.
        private static void RequireStandaloneClipFile(AnimationClip clip, string clipPath)
        {
            if (!clipPath.EndsWith(".anim", StringComparison.OrdinalIgnoreCase) || !AssetDatabase.IsMainAsset(clip))
            {
                throw new ArgumentException(
                    $"'{clipPath}' is not a standalone .anim asset (e.g. it may be embedded in an FBX) "
                    + "and cannot be backed up or restored as a file.");
            }
        }
        // SHARED-ALGORITHM:PathAndModeGuards END

        // Guards against the bridge transport's own retry-on-timeout re-applying a mutation that
        // actually reached Unity the first time (the response was just lost). One JSON file per
        // operationId under Library/Visora/Idempotency/ — survives exactly as long as it needs to
        // (session-lifetime is enough; nothing here claims to survive a project move) and works
        // identically whether called from a compiled class or from a duplicated local function in
        // a freshly-compiled legacy snippet (Task 7), which is the whole reason this is
        // file-based rather than an in-memory Dictionary: that snippet's assembly is thrown away
        // after every single request, so nothing in memory persists between two separate
        // execute_code calls, only the filesystem is shared. `public`, not `private`, because
        // AnimationAuthoringService (Tasks 4-5) calls this cross-class.
        // SHARED-ALGORITHM:IdempotencyCache START
        public static string IdempotencyPath(string operationId) =>
            Path.Combine("Library", "Visora", "Idempotency", operationId + ".json");

        public static bool TryGetCached<T>(string operationId, out T cached)
        {
            cached = default;
            if (string.IsNullOrEmpty(operationId)) return false;
            string path = IdempotencyPath(operationId);
            if (!File.Exists(path)) return false;
            cached = JsonUtility.FromJson<T>(File.ReadAllText(path));
            return true;
        }

        public static void CacheSuccess<T>(string operationId, T result)
        {
            if (string.IsNullOrEmpty(operationId)) return;
            string path = IdempotencyPath(operationId);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, JsonUtility.ToJson(result));
        }
        // SHARED-ALGORITHM:IdempotencyCache END

        // SHARED-ALGORITHM:WriteBackup START
        // Force-saves the clip before copying it: AnimationClip is a live in-memory object once
        // loaded, and Undo.RecordObject/SetEditorCurve mark it dirty without serializing to disk.
        // A backup of stale on-disk bytes can silently discard an earlier, already-succeeded edit
        // the moment someone restores it. Throws on any failure rather than returning an error
        // result, so a caller cannot proceed to edit the clip after a failed backup.

        private static readonly char[] DashSeparator = { '-' };

        public static string WriteBackup(AnimationClip clip, string clipPath, string operation)
        {
            string absoluteClipPath = ResolveProjectPath(clipPath, nameof(clipPath));
            RequireStandaloneClipFile(clip, clipPath);
            if (!File.Exists(absoluteClipPath))
            {
                throw new IOException($"Cannot back up '{clipPath}': file not found at '{absoluteClipPath}'.");
            }

            AssetDatabase.SaveAssetIfDirty(clip);

            string guid = AssetDatabase.AssetPathToGUID(clipPath);
            if (string.IsNullOrEmpty(guid))
            {
                throw new IOException($"Cannot back up '{clipPath}': no AssetDatabase GUID (is it imported?).");
            }

            string clipFolder = Path.Combine(BackupRootPath, guid);
            Directory.CreateDirectory(clipFolder);

            // No internal dash in the timestamp: ParseOperationFromFileName splits on '-' into
            // exactly 3 parts (timestamp, random suffix, operation) and a dash inside the
            // timestamp itself would shift "operation" to include half the random suffix.
            string timestamp = DateTime.UtcNow.ToString("yyyyMMddHHmmssfff", System.Globalization.CultureInfo.InvariantCulture);
            string randomSuffix = Guid.NewGuid().ToString("N").Substring(0, 8);
            string safeOperation = operation.Replace('/', '_').Replace('\\', '_');
            string fileName = $"{timestamp}-{randomSuffix}-{safeOperation}.anim";
            string destination = Path.Combine(clipFolder, fileName);

            File.Copy(absoluteClipPath, destination, overwrite: false);

            return $"{guid}/{fileName}";
        }
        // SHARED-ALGORITHM:WriteBackup END

        // SHARED-ALGORITHM:ListBackups START
        public static ListAnimationBackupsResult ListBackups(string clipPath)
        {
            var result = new ListAnimationBackupsResult { clipPath = clipPath };

            try
            {
                ResolveProjectPath(clipPath, nameof(clipPath));
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            string guid = AssetDatabase.AssetPathToGUID(clipPath);
            string clipFolder = string.IsNullOrEmpty(guid) ? null : Path.Combine(BackupRootPath, guid);

            if (clipFolder == null || !Directory.Exists(clipFolder))
            {
                result.success = true;
                return result;
            }

            try
            {
                var files = Directory.GetFiles(clipFolder, "*.anim")
                    .Select(path => new FileInfo(path))
                    .OrderByDescending(info => info.CreationTimeUtc);

                foreach (var file in files)
                {
                    string backupId = $"{guid}/{file.Name}";
                    string operation = ParseOperationFromFileName(file.Name);
                    result.backups.Add(new AnimationBackupInfo
                    {
                        backupId = backupId,
                        clipPath = clipPath,
                        createdAt = file.CreationTimeUtc.ToString("yyyy-MM-ddTHH:mm:ss.fffZ", System.Globalization.CultureInfo.InvariantCulture),
                        operation = operation,
                        sizeBytes = file.Length,
                    });
                }

                result.success = true;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Failed to list backups for '{clipPath}': {ex.Message}";
            }

            return result;
        }

        private static string ParseOperationFromFileName(string fileName)
        {
            // "<yyyyMMddHHmmssfff>-<8-hex>-<operation>.anim" -> "<operation>"
            string withoutExtension = Path.GetFileNameWithoutExtension(fileName);
            string[] parts = withoutExtension.Split(DashSeparator, 3);
            return parts.Length == 3 ? parts[2] : withoutExtension;
        }
        // SHARED-ALGORITHM:ListBackups END

        // SHARED-ALGORITHM:RestoreBackup START
        public static RestoreAnimationClipResult RestoreBackup(AnimationClip clip, string clipPath, string backupId, string operationId)
        {
            if (TryGetCached(operationId, out RestoreAnimationClipResult cached))
            {
                return cached;
            }

            var result = new RestoreAnimationClipResult { clipPath = clipPath };

            string editModeError = CheckEditMode();
            if (editModeError != null)
            {
                result.success = false;
                result.error = editModeError;
                return result;
            }

            string absoluteClipPath;
            string backupPath;

            try
            {
                absoluteClipPath = ResolveProjectPath(clipPath, nameof(clipPath));
                backupPath = ResolveBackupPath(backupId);
                RequireStandaloneClipFile(clip, clipPath);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = ex.Message;
                return result;
            }

            if (!File.Exists(backupPath))
            {
                result.success = false;
                result.error = $"Backup '{backupId}' not found.";
                return result;
            }

            // The backup's folder name is the clip's GUID: reject a backup taken of a different
            // clip rather than silently overwriting this one with unrelated content.
            string expectedGuid = AssetDatabase.AssetPathToGUID(clipPath);
            string actualGuid = Path.GetFileName(Path.GetDirectoryName(backupPath));
            if (!string.Equals(expectedGuid, actualGuid, StringComparison.OrdinalIgnoreCase))
            {
                result.success = false;
                result.error = $"Backup '{backupId}' belongs to a different clip than '{clipPath}'.";
                return result;
            }

            string tempPath = absoluteClipPath + ".visora-restore-tmp";
            string preRestoreBackupId = null;

            try
            {
                // A restore is itself a mutation: snapshot the state it is about to discard first,
                // so the restore can be undone the same way any other edit can, and so a failed
                // import below has something exact to roll back to.
                preRestoreBackupId = WriteBackup(clip, clipPath, "restore_animation_clip");

                // Atomic swap: copy to a temp file beside the target, then File.Replace, which
                // either fully succeeds or leaves the original file untouched. A bare
                // File.Copy(overwrite: true) has no such guarantee if it fails partway through.
                File.Copy(backupPath, tempPath, overwrite: true);
                File.Replace(tempPath, absoluteClipPath, null);

                try
                {
                    AssetDatabase.ImportAsset(clipPath, ImportAssetOptions.ForceUpdate);
                }
                catch (Exception importEx)
                {
                    // The file swap already succeeded, so the working file is the restored one —
                    // but Unity's asset database may now disagree with what's on disk. Roll the
                    // file back to the state just before this restore attempt rather than leaving
                    // a half-applied restore behind.
                    string preRestorePath = Path.Combine(BackupRootPath, preRestoreBackupId);
                    File.Copy(preRestorePath, absoluteClipPath, overwrite: true);
                    AssetDatabase.ImportAsset(clipPath, ImportAssetOptions.ForceUpdate);
                    throw new IOException($"Import failed after file swap; rolled back to the pre-restore state: {importEx.Message}");
                }

                result.preRestoreBackupId = preRestoreBackupId;
                result.restoredFromBackupId = backupId;
                result.success = true;
                CacheSuccess(operationId, result);
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Failed to restore '{clipPath}' from '{backupId}': {ex.Message}";
                result.preRestoreBackupId = preRestoreBackupId;
            }
            finally
            {
                if (File.Exists(tempPath))
                {
                    File.Delete(tempPath);
                }
            }

            return result;
        }
    }
}
