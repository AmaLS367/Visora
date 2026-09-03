using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
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
        private static readonly List<SteppedRoutine> ActiveRoutines = new List<SteppedRoutine>();

        private sealed class SteppedRoutine
        {
            public IEnumerator Routine;
            public Action OnCompleted;
            public Action<Exception> OnFailed;
        }

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

            StepRoutines();
        }

        /// <summary>
        /// Advances every active stepped routine by exactly one step per editor update tick, so a
        /// routine can span many frames of real editor time instead of blocking a single tick.
        /// </summary>
        private static void StepRoutines()
        {
            if (ActiveRoutines.Count == 0) return;

            for (int i = ActiveRoutines.Count - 1; i >= 0; i--)
            {
                var entry = ActiveRoutines[i];
                bool hasMore;

                try
                {
                    hasMore = entry.Routine.MoveNext();
                }
                catch (Exception ex)
                {
                    ActiveRoutines.RemoveAt(i);
                    (entry.Routine as IDisposable)?.Dispose();
                    entry.OnFailed?.Invoke(ex);
                    continue;
                }

                if (!hasMore)
                {
                    ActiveRoutines.RemoveAt(i);
                    entry.OnCompleted?.Invoke();
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

        /// <summary>
        /// Runs a routine on the Editor main thread one step per update tick, then resolves with
        /// resultSelector. Use this - not EnqueueAsync - whenever the work must observe real editor
        /// time passing between steps, such as recording animation frames at a target frame rate.
        /// </summary>
        public static Task<T> EnqueueSteppedAsync<T>(Func<IEnumerator> routineFactory, Func<T> resultSelector)
        {
            var tcs = new TaskCompletionSource<T>();

            Post(() =>
            {
                IEnumerator routine;
                try
                {
                    routine = routineFactory();
                }
                catch (Exception ex)
                {
                    tcs.SetException(ex);
                    return;
                }

                if (routine == null)
                {
                    try
                    {
                        tcs.SetResult(resultSelector());
                    }
                    catch (Exception ex)
                    {
                        tcs.SetException(ex);
                    }
                    return;
                }

                ActiveRoutines.Add(new SteppedRoutine
                {
                    Routine = routine,
                    OnCompleted = () =>
                    {
                        try
                        {
                            tcs.SetResult(resultSelector());
                        }
                        catch (Exception ex)
                        {
                            tcs.SetException(ex);
                        }
                    },
                    OnFailed = ex => tcs.SetException(ex)
                });
            });

            return tcs.Task;
        }
    }
}
