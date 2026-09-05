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
        private static readonly StringComparison PathComparison =
            Application.platform == RuntimePlatform.WindowsEditor ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;

        private static string ResolveProjectPath(string relativePath, string paramName)
        {
            string projectRoot = Path.GetFullPath(ProjectRoot) + Path.DirectorySeparatorChar;
            string resolved = Path.GetFullPath(Path.Combine(ProjectRoot, relativePath ?? string.Empty));
            if (!resolved.StartsWith(projectRoot, PathComparison))
            {
                throw new ArgumentException($"{paramName} '{relativePath}' resolves outside the project.");
            }
            return resolved;
        }

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
            if (!resolved.StartsWith(backupRoot, PathComparison))
            {
                throw new ArgumentException($"backupId '{backupId}' resolves outside VisoraBackups/.");
            }
            return resolved;
        }

        private static void RequireStandaloneClipFile(AnimationClip clip, string clipPath)
        {
            if (!clipPath.EndsWith(".anim", StringComparison.OrdinalIgnoreCase) || !AssetDatabase.IsMainAsset(clip))
            {
                throw new ArgumentException(
                    $"'{clipPath}' is not a standalone .anim asset (e.g. it may be embedded in an FBX) "
                    + "and cannot be backed up or restored as a file.");
            }
        }

        private static readonly System.Text.RegularExpressions.Regex SafeOperationIdRegex =
            new System.Text.RegularExpressions.Regex(@"^[a-zA-Z0-9_\-]+$", System.Text.RegularExpressions.RegexOptions.Compiled);

        public static string IdempotencyPath(string operationId)
        {
            if (string.IsNullOrEmpty(operationId) || !SafeOperationIdRegex.IsMatch(operationId))
            {
                throw new ArgumentException($"Invalid operationId '{operationId}'. Must contain only alphanumeric characters, underscores, or hyphens.", nameof(operationId));
            }
            return Path.Combine("Library", "Visora", "Idempotency", Path.GetFileName(operationId) + ".json");
        }

        public static bool TryGetCached<T>(string operationId, out T cached)
        {
            cached = default;
            if (string.IsNullOrEmpty(operationId) || !SafeOperationIdRegex.IsMatch(operationId)) return false;
            string path = IdempotencyPath(operationId);
            if (!File.Exists(path)) return false;
            cached = JsonUtility.FromJson<T>(File.ReadAllText(path));
            return true;
        }

        public static void CacheSuccess<T>(string operationId, T result)
        {
            if (string.IsNullOrEmpty(operationId) || !SafeOperationIdRegex.IsMatch(operationId)) return;
            string path = IdempotencyPath(operationId);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, JsonUtility.ToJson(result));
        }

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

            string timestamp = DateTime.UtcNow.ToString("yyyyMMddHHmmssfff", System.Globalization.CultureInfo.InvariantCulture);
            string randomSuffix = Guid.NewGuid().ToString("N").Substring(0, 8);
            string safeOperation = operation.Replace('/', '_').Replace('\\', '_');
            string fileName = $"{timestamp}-{randomSuffix}-{safeOperation}.anim";
            string destination = Path.Combine(clipFolder, fileName);

            File.Copy(absoluteClipPath, destination, overwrite: false);

            return $"{guid}/{fileName}";
        }

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
                    .OrderByDescending(info => info.Name)
                    .ThenByDescending(info => info.CreationTimeUtc);

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

        private static readonly char[] DashSeparator = { '-' };

        private static string ParseOperationFromFileName(string fileName)
        {
            // "<yyyyMMddHHmmssfff>-<8-hex>-<operation>.anim" -> "<operation>"
            string withoutExtension = Path.GetFileNameWithoutExtension(fileName);
            string[] parts = withoutExtension.Split(DashSeparator, 3);
            return parts.Length == 3 ? parts[2] : withoutExtension;
        }

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
