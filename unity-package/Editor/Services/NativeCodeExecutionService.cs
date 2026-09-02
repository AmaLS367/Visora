using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEngine;
using Visora.Editor.Core;

namespace Visora.Editor.Services
{
    /// <summary>
    /// Executes the statement-body snippets accepted by the legacy AnkleBreaker bridge.
    /// Sources and assemblies are isolated below Library/Visora and removed after every request.
    /// </summary>
    internal static class NativeCodeExecutionService
    {
        private static readonly SemaphoreSlim ExecutionLock = new SemaphoreSlim(1, 1);

        public static async Task<Dictionary<string, object>> ExecuteAsync(string code, float timeoutSeconds)
        {
            var timeout = Mathf.Clamp(timeoutSeconds, 1f, 300f);
            await ExecutionLock.WaitAsync();
            var logs = new List<string>();
            Application.LogCallback callback = (condition, _, type) => logs.Add($"{type}: {condition}");
            Application.logMessageReceivedThreaded += callback;

            string sourcePath = null;
            string assemblyPath = null;
            try
            {
                var operationId = Guid.NewGuid().ToString("N");
                var workDirectory = Path.Combine("Library", "Visora", "Executor");
                Directory.CreateDirectory(workDirectory);
                sourcePath = Path.Combine(workDirectory, $"VisoraSnippet_{operationId}.cs");
                assemblyPath = Path.Combine(workDirectory, $"VisoraSnippet_{operationId}.dll");
                var typeName = $"VisoraSnippet_{operationId}";
                File.WriteAllText(sourcePath, BuildSource(typeName, code));

                var compilation = await CompileAsync(sourcePath, assemblyPath, timeout);
                if (compilation.errors.Count > 0)
                {
                    return Failure("Compilation failed", compilation.errors, logs);
                }

                var result = await MainThreadDispatcher.EnqueueAsync(() => Invoke(assemblyPath, typeName));
                return new Dictionary<string, object>
                {
                    { "success", true }, { "result", result }, { "logs", logs }
                };
            }
            catch (TimeoutException)
            {
                return Failure($"Code execution timed out after {timeout:0.###} seconds", null, logs);
            }
            catch (Exception exception)
            {
                return Failure(exception.Message, null, logs);
            }
            finally
            {
                Application.logMessageReceivedThreaded -= callback;
                Cleanup(sourcePath);
                Cleanup(assemblyPath);
                Cleanup(assemblyPath == null ? null : Path.ChangeExtension(assemblyPath, ".pdb"));
                ExecutionLock.Release();
            }
        }

        private static string BuildSource(string typeName, string body)
        {
            return $@"using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
internal static class {typeName}
{{
    public static object Execute()
    {{
        {body}
        return null;
    }}
}}";
        }

        private static async Task<(List<string> errors, bool started)> CompileAsync(
            string sourcePath, string assemblyPath, float timeoutSeconds)
        {
            var completion = new TaskCompletionSource<List<string>>();
            await MainThreadDispatcher.EnqueueAsync(() =>
            {
                var builder = new AssemblyBuilder(assemblyPath, new[] { sourcePath })
                {
                    referencesOptions = ReferencesOptions.UseEngineModules,
                    additionalReferences = CompilationPipeline.GetAssemblies()
                        .Select(assembly => assembly.outputPath)
                        .Where(path => !string.IsNullOrEmpty(path))
                        .ToArray()
                };
                builder.buildFinished += (_, messages) => completion.TrySetResult(messages
                    .Where(message => message.type == CompilerMessageType.Error)
                    .Select(message => $"{message.file}({message.line},{message.column}): {message.message}")
                    .ToList());
                if (!builder.Build()) completion.TrySetResult(new List<string> { "Unity rejected the dynamic assembly build." });
            });

            var timeoutTask = Task.Delay(TimeSpan.FromSeconds(timeoutSeconds));
            if (await Task.WhenAny(completion.Task, timeoutTask) != completion.Task) throw new TimeoutException();
            return (await completion.Task, true);
        }

        private static object Invoke(string assemblyPath, string typeName)
        {
            // Qualified because both `using System.Reflection;` and `using UnityEditor.Compilation;`
            // (needed above for CompilationPipeline/AssemblyBuilder) declare an `Assembly` type -
            // the bare name is a compile error (CS0104), not just a style choice.
            var assembly = System.Reflection.Assembly.Load(File.ReadAllBytes(assemblyPath));
            var method = assembly.GetType(typeName)?.GetMethod("Execute", BindingFlags.Public | BindingFlags.Static);
            if (method == null) throw new InvalidOperationException("Compiled Visora snippet has no Execute method.");
            return method.Invoke(null, null);
        }

        private static Dictionary<string, object> Failure(string error, List<string> compilationErrors, List<string> logs)
        {
            var result = new Dictionary<string, object> { { "success", false }, { "error", error }, { "logs", logs } };
            if (compilationErrors != null) result["compilationErrors"] = compilationErrors;
            return result;
        }

        private static void Cleanup(string path)
        {
            if (string.IsNullOrEmpty(path)) return;
            try { if (File.Exists(path)) File.Delete(path); }
            catch (Exception exception) { Debug.LogWarning($"[Visora] Could not clean executor artifact '{path}': {exception.Message}"); }
        }
    }
}
