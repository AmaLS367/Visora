using UnityEditor;

namespace Visora.Editor.Core
{
    /// <summary>
    /// Configuration settings for the Visora Unity Editor server.
    /// </summary>
    public static class VisoraSettings
    {
        private const string PrefKeyPort = "Visora_Server_Port";
        private const string PrefKeyAutoStart = "Visora_Server_AutoStart";
        private const string PrefKeyVerboseLogs = "Visora_Server_VerboseLogs";

        public static int ServerPort
        {
            get => EditorPrefs.GetInt(PrefKeyPort, 7890);
            set => EditorPrefs.SetInt(PrefKeyPort, value);
        }

        public static bool AutoStart
        {
            get => EditorPrefs.GetBool(PrefKeyAutoStart, true);
            set => EditorPrefs.SetBool(PrefKeyAutoStart, value);
        }

        public static bool VerboseLogs
        {
            get => EditorPrefs.GetBool(PrefKeyVerboseLogs, false);
            set => EditorPrefs.SetBool(PrefKeyVerboseLogs, value);
        }
    }
}
