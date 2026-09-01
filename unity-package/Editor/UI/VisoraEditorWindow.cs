using UnityEditor;
using UnityEngine;
using Visora.Editor.Core;

namespace Visora.Editor.UI
{
    /// <summary>
    /// Unity Editor Window for monitoring and configuring the Visora Editor bridge.
    /// </summary>
    public class VisoraEditorWindow : EditorWindow
    {
        private int _port;
        private bool _autoStart;
        private bool _verboseLogs;

        [MenuItem("Window/Visora/Server Monitor", false, 1000)]
        public static void ShowWindow()
        {
            var window = GetWindow<VisoraEditorWindow>("Visora Monitor");
            window.minSize = new Vector2(360, 280);
            window.Show();
        }

        private void OnEnable()
        {
            _port = VisoraSettings.ServerPort;
            _autoStart = VisoraSettings.AutoStart;
            _verboseLogs = VisoraSettings.VerboseLogs;
        }

        private void OnGUI()
        {
            GUILayout.Space(10);
            EditorGUILayout.LabelField("Visora Editor Bridge", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox("Visora connects AI agents to Unity Editor via a high-performance native HTTP bridge.", MessageType.Info);

            GUILayout.Space(10);
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            
            bool isRunning = VisoraServer.IsRunning;
            var statusColor = isRunning ? new Color(0.2f, 0.8f, 0.2f) : new Color(0.8f, 0.2f, 0.2f);
            var statusText = isRunning ? $"Running (Port {VisoraServer.ActivePort})" : "Stopped";

            var origColor = GUI.color;
            GUI.color = statusColor;
            EditorGUILayout.LabelField($"Status: {statusText}", EditorStyles.boldLabel);
            GUI.color = origColor;

            EditorGUILayout.EndVertical();

            GUILayout.Space(10);
            EditorGUILayout.LabelField("Configuration", EditorStyles.boldLabel);

            EditorGUI.BeginChangeCheck();
            _port = EditorGUILayout.IntField("Server Port", _port);
            _autoStart = EditorGUILayout.Toggle("Auto Start on Load", _autoStart);
            _verboseLogs = EditorGUILayout.Toggle("Verbose Logging", _verboseLogs);

            if (EditorGUI.EndChangeCheck())
            {
                VisoraSettings.ServerPort = _port;
                VisoraSettings.AutoStart = _autoStart;
                VisoraSettings.VerboseLogs = _verboseLogs;
            }

            GUILayout.Space(15);
            EditorGUILayout.BeginHorizontal();

            if (!isRunning)
            {
                if (GUILayout.Button("Start Server", GUILayout.Height(28)))
                {
                    VisoraServer.Start(_port);
                }
            }
            else
            {
                if (GUILayout.Button("Restart Server", GUILayout.Height(28)))
                {
                    VisoraServer.Restart(_port);
                }
                if (GUILayout.Button("Stop Server", GUILayout.Height(28)))
                {
                    VisoraServer.Stop();
                }
            }

            EditorGUILayout.EndHorizontal();

            GUILayout.FlexibleSpace();
            EditorGUILayout.LabelField("Visora v1.0.0 | UPM Package", EditorStyles.miniLabel);
        }
    }
}
