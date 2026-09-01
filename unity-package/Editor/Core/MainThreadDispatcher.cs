using System;
using System.Collections.Concurrent;
using System.Threading.Tasks;
using UnityEditor;

namespace Visora.Editor.Core
{
    /// <summary>
    /// Dispatches actions and async tasks from background HTTP threads onto the Unity Editor main thread.
    /// </summary>
    [InitializeOnLoad]
    public static class MainThreadDispatcher
    {
        private static readonly ConcurrentQueue<Action> ExecutionQueue = new ConcurrentQueue<Action>();

        static MainThreadDispatcher()
        {
            EditorApplication.update -= Update;
            EditorApplication.update += Update;
        }

        private static void Update()
        {
            while (ExecutionQueue.TryDequeue(out var action))
            {
                try
                {
                    action?.Invoke();
                }
                catch (Exception ex)
                {
                    UnityEngine.Debug.LogError($"[Visora] Error executing task on MainThread: {ex}");
                }
            }
        }

        /// <summary>
        /// Post an action to be executed on the Editor main thread.
        /// </summary>
        public static void Post(Action action)
        {
            if (action == null) return;
            ExecutionQueue.Enqueue(action);
        }

        /// <summary>
        /// Executes a function on the Editor main thread and returns the result asynchronously.
        /// </summary>
        public static Task<T> EnqueueAsync<T>(Func<T> function)
        {
            var tcs = new TaskCompletionSource<T>();
            Post(() =>
            {
                try
                {
                    var result = function();
                    tcs.SetResult(result);
                }
                catch (Exception ex)
                {
                    tcs.SetException(ex);
                }
            });
            return tcs.Task;
        }

        /// <summary>
        /// Executes an action on the Editor main thread asynchronously.
        /// </summary>
        public static Task EnqueueAsync(Action action)
        {
            var tcs = new TaskCompletionSource<bool>();
            Post(() =>
            {
                try
                {
                    action();
                    tcs.SetResult(true);
                }
                catch (Exception ex)
                {
                    tcs.SetException(ex);
                }
            });
            return tcs.Task;
        }
    }
}
