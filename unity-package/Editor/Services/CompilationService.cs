using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.Compilation;

namespace Visora.Editor.Services
{
    [Serializable]
    public class CompilerMessageData
    {
        public string type;
        public string message;
        public string file;
        public int line;
        public int column;
    }

    [Serializable]
    public class CompilationStatusResult
    {
        public bool success;
        public bool isCompiling;
        public int errorCount;
        public int warningCount;
        public List<CompilerMessageData> messages = new List<CompilerMessageData>();
    }

    /// <summary>
    /// Tracks and provides compilation errors and warnings from Unity's CompilationPipeline.
    /// </summary>
    [InitializeOnLoad]
    public static class CompilationService
    {
        private static readonly List<CompilerMessageData> CachedMessages = new List<CompilerMessageData>();

        static CompilationService()
        {
            CompilationPipeline.assemblyCompilationFinished -= OnAssemblyCompilationFinished;
            CompilationPipeline.assemblyCompilationFinished += OnAssemblyCompilationFinished;
        }

        private static void OnAssemblyCompilationFinished(string assemblyPath, CompilerMessage[] messages)
        {
            if (messages == null || messages.Length == 0) return;

            lock (CachedMessages)
            {
                foreach (var msg in messages)
                {
                    CachedMessages.Add(new CompilerMessageData
                    {
                        type = msg.type.ToString(),
                        message = msg.message,
                        file = msg.file,
                        line = msg.line,
                        column = msg.column
                    });
                }

                // Trim cache size if it gets too large
                if (CachedMessages.Count > 100)
                {
                    CachedMessages.RemoveRange(0, CachedMessages.Count - 100);
                }
            }
        }

        public static CompilationStatusResult GetCompilationStatus()
        {
            var result = new CompilationStatusResult
            {
                success = true,
                isCompiling = EditorApplication.isCompiling
            };

            lock (CachedMessages)
            {
                result.messages.AddRange(CachedMessages);
            }

            foreach (var m in result.messages)
            {
                if (m.type == "Error") result.errorCount++;
                else if (m.type == "Warning") result.warningCount++;
            }

            return result;
        }

        public static void ClearMessages()
        {
            lock (CachedMessages)
            {
                CachedMessages.Clear();
            }
        }
    }
}
