using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Visora.Editor.Services
{
    [Serializable]
    public class TransactionResult
    {
        public bool success;
        public string error;
        public string transactionId;
        public int undoGroupId;
        public string description;
        public bool isPlayMode;
        public string scenePath;
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Manages safe scene operations, Undo transactions, and rollbacks on the Unity Editor side.
    /// </summary>
    public static class SceneTransactionService
    {
        private static readonly Dictionary<string, int> ActiveTransactions = new Dictionary<string, int>();

        public static TransactionResult BeginTransaction(string description = "Visora Agent Operation")
        {
            var result = new TransactionResult
            {
                description = description,
                isPlayMode = EditorApplication.isPlaying,
                scenePath = SceneManager.GetActiveScene().path
            };

            if (EditorApplication.isPlaying)
            {
                result.warnings.Add("Operation started in Play Mode. Scene modifications won't persist after exiting Play Mode.");
            }

            try
            {
                Undo.IncrementCurrentGroup();
                int groupId = Undo.GetCurrentGroup();
                Undo.SetCurrentGroupName(description);

                string transactionId = "tx_" + Guid.NewGuid().ToString("N").Substring(0, 8);
                ActiveTransactions[transactionId] = groupId;

                result.success = true;
                result.transactionId = transactionId;
                result.undoGroupId = groupId;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Failed to begin transaction: {ex.Message}";
            }

            return result;
        }

        public static TransactionResult CommitTransaction(string transactionId, bool saveScene = false)
        {
            var result = new TransactionResult
            {
                transactionId = transactionId,
                isPlayMode = EditorApplication.isPlaying,
                scenePath = SceneManager.GetActiveScene().path
            };

            if (!ActiveTransactions.TryGetValue(transactionId, out var groupId))
            {
                result.success = false;
                result.error = $"Transaction ID '{transactionId}' not found or already closed.";
                return result;
            }

            try
            {
                Undo.CollapseUndoOperations(groupId);
                ActiveTransactions.Remove(transactionId);
                result.undoGroupId = groupId;
                result.success = true;

                if (saveScene && !EditorApplication.isPlaying)
                {
                    var scene = SceneManager.GetActiveScene();
                    if (scene.isDirty)
                    {
                        EditorSceneManager.SaveScene(scene);
                    }
                }
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Failed to commit transaction: {ex.Message}";
            }

            return result;
        }

        public static TransactionResult RollbackTransaction(string transactionId)
        {
            var result = new TransactionResult
            {
                transactionId = transactionId,
                isPlayMode = EditorApplication.isPlaying,
                scenePath = SceneManager.GetActiveScene().path
            };

            if (!ActiveTransactions.TryGetValue(transactionId, out var groupId))
            {
                result.success = false;
                result.error = $"Transaction ID '{transactionId}' not found or already closed.";
                return result;
            }

            try
            {
                Undo.RevertAllDownToGroup(groupId);
                ActiveTransactions.Remove(transactionId);
                result.undoGroupId = groupId;
                result.success = true;
            }
            catch (Exception ex)
            {
                result.success = false;
                result.error = $"Failed to rollback transaction: {ex.Message}";
            }

            return result;
        }
    }
}
