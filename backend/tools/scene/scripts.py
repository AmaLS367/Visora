import json


def _get_scene_details_code() -> str:
    """C# snippet to inspect active scene and editor state."""
    return """
var activeScene = UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
return new System.Collections.Generic.Dictionary<string, object>
{
    { "sceneName", activeScene.name },
    { "scenePath", activeScene.path },
    { "isDirty", activeScene.isDirty },
    { "sceneCount", UnityEditor.SceneManagement.EditorSceneManager.sceneCount },
    { "isPlaying", UnityEditor.EditorApplication.isPlaying },
    { "isPaused", UnityEditor.EditorApplication.isPaused },
    { "isCompiling", UnityEditor.EditorApplication.isCompiling },
    { "isUpdating", UnityEditor.EditorApplication.isUpdating },
};
"""


def _save_scene_code(target_path: str | None = None) -> str:
    """C# snippet to save active scene safely."""
    path_literal = json.dumps(target_path) if target_path else "null"
    return f"""
var targetPath = {path_literal};
var activeScene = UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
var wasDirty = activeScene.isDirty;
bool saved;
if (string.IsNullOrEmpty(targetPath))
{{
    saved = UnityEditor.SceneManagement.EditorSceneManager.SaveScene(activeScene);
}}
else
{{
    saved = UnityEditor.SceneManagement.EditorSceneManager.SaveScene(activeScene, targetPath);
}}
return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "saved", saved }},
    {{ "wasDirty", wasDirty }},
    {{ "sceneName", activeScene.name }},
    {{ "scenePath", string.IsNullOrEmpty(targetPath) ? activeScene.path : targetPath }},
}};
"""


def _begin_undo_group_code(undo_name: str) -> str:
    """C# snippet to create and name a new Undo group."""
    name_literal = json.dumps(undo_name)
    return f"""
UnityEditor.Undo.IncrementCurrentGroup();
UnityEditor.Undo.SetCurrentGroupName({name_literal});
var currentGroup = UnityEditor.Undo.GetCurrentGroup();
return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "undoGroup", currentGroup }},
}};
"""


def _undo_transaction_code(undo_group: int) -> str:
    """C# snippet to revert changes down to an Undo group."""
    return f"""
UnityEditor.Undo.RevertAllDownToGroup({undo_group});
return new System.Collections.Generic.Dictionary<string, object>
{{
    {{ "reverted", true }},
    {{ "undoGroup", {undo_group} }},
}};
"""


def _reload_scene_code() -> str:
    """C# snippet to reload active scene from disk."""
    return """
var activeScene = UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
if (string.IsNullOrEmpty(activeScene.path))
{
    throw new System.Exception("Active scene has never been saved to disk and cannot be reloaded.");
}
var opened = UnityEditor.SceneManagement.EditorSceneManager.OpenScene(activeScene.path, UnityEditor.SceneManagement.OpenSceneMode.Single);
return new System.Collections.Generic.Dictionary<string, object>
{
    { "reloaded", opened.IsValid() },
    { "sceneName", opened.name },
    { "scenePath", opened.path },
};
"""
