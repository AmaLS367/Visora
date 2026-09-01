using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    public enum TaskStatus
    {
        Pending,
        Running,
        Completed,
        Failed,
        Cancelled
    }

    [Serializable]
    public class TaskTicket
    {
        public string ticketId;
        public string status;
        public float progress;
        public string message;
        public string resultJson;
        public string error;
        public double startTime;
        public double endTime;
        public bool isDone;
    }

    /// <summary>
    /// Manages long-running asynchronous Editor tasks and coroutines with ticket-based tracking.
    /// </summary>
    [InitializeOnLoad]
    public static class EditorTaskQueue
    {
        private static readonly ConcurrentDictionary<string, TaskTicket> Tickets = new ConcurrentDictionary<string, TaskTicket>();
        private static readonly List<IEnumerator> ActiveCoroutines = new List<IEnumerator>();
        private static readonly Dictionary<IEnumerator, string> CoroutineTicketMap = new Dictionary<IEnumerator, string>();

        static EditorTaskQueue()
        {
            EditorApplication.update -= UpdateCoroutines;
            EditorApplication.update += UpdateCoroutines;
        }

        private static void UpdateCoroutines()
        {
            if (ActiveCoroutines.Count == 0) return;

            for (int i = ActiveCoroutines.Count - 1; i >= 0; i--)
            {
                var coroutine = ActiveCoroutines[i];
                string ticketId = CoroutineTicketMap.TryGetValue(coroutine, out var tid) ? tid : null;

                try
                {
                    if (ticketId != null && Tickets.TryGetValue(ticketId, out var ticket) && ticket.status == TaskStatus.Cancelled.ToString())
                    {
                        ActiveCoroutines.RemoveAt(i);
                        CoroutineTicketMap.Remove(coroutine);
                        continue;
                    }

                    if (!coroutine.MoveNext())
                    {
                        ActiveCoroutines.RemoveAt(i);
                        CoroutineTicketMap.Remove(coroutine);

                        if (ticketId != null && Tickets.TryGetValue(ticketId, out var doneTicket))
                        {
                            if (doneTicket.status != TaskStatus.Cancelled.ToString() && doneTicket.status != TaskStatus.Failed.ToString())
                            {
                                doneTicket.status = TaskStatus.Completed.ToString();
                                doneTicket.progress = 1.0f;
                                doneTicket.isDone = true;
                                doneTicket.endTime = EditorApplication.timeSinceStartup;
                            }
                        }
                    }
                }
                catch (Exception ex)
                {
                    ActiveCoroutines.RemoveAt(i);
                    CoroutineTicketMap.Remove(coroutine);

                    if (ticketId != null && Tickets.TryGetValue(ticketId, out var failTicket))
                    {
                        failTicket.status = TaskStatus.Failed.ToString();
                        failTicket.error = ex.ToString();
                        failTicket.isDone = true;
                        failTicket.endTime = EditorApplication.timeSinceStartup;
                    }
                    Debug.LogError($"[Visora] Error in Editor Coroutine (ticket={ticketId}): {ex}");
                }
            }
        }

        public static string EnqueueTask(IEnumerator coroutine, string description = "")
        {
            string ticketId = "ticket_" + Guid.NewGuid().ToString("N").Substring(0, 8);
            var ticket = new TaskTicket
            {
                ticketId = ticketId,
                status = TaskStatus.Running.ToString(),
                progress = 0.0f,
                message = description,
                startTime = EditorApplication.timeSinceStartup,
                isDone = false
            };

            Tickets[ticketId] = ticket;
            ActiveCoroutines.Add(coroutine);
            CoroutineTicketMap[coroutine] = ticketId;

            return ticketId;
        }

        public static TaskTicket GetTicketStatus(string ticketId)
        {
            if (string.IsNullOrEmpty(ticketId)) return null;
            Tickets.TryGetValue(ticketId, out var ticket);
            return ticket;
        }

        public static bool CancelTask(string ticketId)
        {
            if (string.IsNullOrEmpty(ticketId)) return false;
            if (Tickets.TryGetValue(ticketId, out var ticket))
            {
                if (!ticket.isDone)
                {
                    ticket.status = TaskStatus.Cancelled.ToString();
                    ticket.isDone = true;
                    ticket.endTime = EditorApplication.timeSinceStartup;
                    return true;
                }
            }
            return false;
        }

        public static void UpdateTicketProgress(string ticketId, float progress, string message = null, string resultJson = null)
        {
            if (Tickets.TryGetValue(ticketId, out var ticket))
            {
                ticket.progress = Mathf.Clamp01(progress);
                if (message != null) ticket.message = message;
                if (resultJson != null) ticket.resultJson = resultJson;
            }
        }
    }
}
