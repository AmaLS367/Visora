using System;
using System.Net;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Core
{
    /// <summary>
    /// Core HTTP server running in Unity Editor process.
    /// Listens for requests from the Visora Python MCP server and agent tools.
    /// </summary>
    [InitializeOnLoad]
    public static class VisoraServer
    {
        private static HttpListener _listener;
        private static CancellationTokenSource _cts;
        private static bool _isRunning;
        private static int _activePort;

        public static bool IsRunning => _isRunning;
        public static int ActivePort => _activePort;

        static VisoraServer()
        {
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.quitting += Stop;

            if (VisoraSettings.AutoStart)
            {
                EditorApplication.delayCall += () =>
                {
                    Start(VisoraSettings.ServerPort);
                };
            }
        }

        public static bool Start(int port = 7890)
        {
            if (_isRunning)
            {
                if (_activePort == port) return true;
                Stop();
            }

            _cts = new CancellationTokenSource();
            _listener = new HttpListener();

            try
            {
                _listener.Prefixes.Add($"http://127.0.0.1:{port}/");
                _listener.Prefixes.Add($"http://localhost:{port}/");
                _listener.Start();

                _activePort = port;
                _isRunning = true;

                Task.Run(() => ListenLoop(_listener, _cts.Token));
                Debug.Log($"<color=#4CAF50><b>[Visora]</b></color> Native Editor Bridge started on port {port}");
                return true;
            }
            catch (Exception ex)
            {
                Debug.LogError($"[Visora] Failed to start HTTP server on port {port}: {ex.Message}");
                Stop();
                return false;
            }
        }

        public static void Stop()
        {
            if (!_isRunning) return;

            try
            {
                _cts?.Cancel();
                if (_listener != null && _listener.IsListening)
                {
                    _listener.Stop();
                    _listener.Close();
                }
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Visora] Warning during server shutdown: {ex.Message}");
            }
            finally
            {
                _listener = null;
                _cts = null;
                _isRunning = false;
                Debug.Log("[Visora] Native Editor Bridge stopped.");
            }
        }

        public static void Restart(int port = 7890)
        {
            Stop();
            Start(port);
        }

        private static async Task ListenLoop(HttpListener listener, CancellationToken token)
        {
            while (!token.IsCancellationRequested && listener != null && listener.IsListening)
            {
                try
                {
                    var context = await listener.GetContextAsync();
                    _ = Task.Run(() => VisoraHttpRouter.HandleRequestAsync(context), token);
                }
                catch (HttpListenerException)
                {
                    // Listener stopped or aborted
                    break;
                }
                catch (ObjectDisposedException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    if (!token.IsCancellationRequested)
                    {
                        Debug.LogError($"[Visora] Error accepting HTTP connection: {ex}");
                    }
                }
            }
        }
    }
}
