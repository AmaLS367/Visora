# Visora Editor Bridge (`com.visora.editor`)

A high-performance, native Unity Editor bridge for the Visora AI Agent MCP Server.

## Features

- **Built-in HTTP Server:** Lightweight, non-blocking HTTP listener integrated directly into the Unity Editor update loop.
- **Native Camera Rendering:** High-resolution single and sequence screenshot capture with direct RenderTexture blitting and Base64 PNG/JPG encoding without runtime C# compilation overhead.
- **Editor Task Queue:** Native coroutine and background task execution with ticket-based status polling, cancellation, and progress reporting.
- **Scene Transaction Manager:** Safe Undo group tracking, dirty state management, and rollback mechanisms for agent operations.
- **Persistent Diagnostics:** Non-destructive mesh validation (normals, bounds, bone weights, submeshes), skeleton/rig intelligence, and AnimationClip curve inspection.
- **Full Backward Compatibility:** Implements standard AnkleBreaker bridge endpoints alongside high-performance native `/api/visora/*` endpoints.

## Installation

### Via Unity Package Manager (Git URL)
1. In Unity Editor, open **Window > Package Manager**.
2. Click the **+** icon and select **Add package from git URL...**.
3. Enter: `https://github.com/AmaLS367/Visora.git?path=unity-package`

### Via Local Path
Add the local package in your project's `Packages/manifest.json`:
```json
{
  "dependencies": {
    "com.visora.editor": "file:../../Visora/unity-package"
  }
}
```

## Editor Window

Open **Window > Visora > Server Monitor** to view server status, active port, received requests, and configuration settings.
