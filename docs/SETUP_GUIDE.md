# Visora — Setup & Integration Guide ⚙️

This document explains how to set up **Visora**, configure its connection to Unity Editor via the **AnkleBreaker HTTP bridge**, and connect it to various **AI Agent clients** (Claude Desktop, Cursor, Antigravity, OpenCode, and CLI).

---

## 📑 Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Unity Editor & AnkleBreaker Setup](#2-unity-editor--anklebreaker-setup)
3. [Environment Configuration (`.env`)](#3-environment-configuration-env)
4. [Connecting MCP Clients](#4-connecting-mcp-clients)
   - [Claude Desktop](#claude-desktop)
   - [Cursor / Windsurf](#cursor--windsurf)
   - [Antigravity / OpenCode](#antigravity--opencode)
   - [CLI / Standalone Mode](#cli--standalone-mode)
5. [Bridge Health & Troubleshooting](#5-bridge-health--troubleshooting)

---

## 1. Prerequisites

- **Python 3.10+** (managed via [`uv`](https://github.com/astral-sh/uv) recommended)
- **Unity 2021.3 LTS or newer** (Unity 2022 LTS / Unity 6 supported)
- **AnkleBreaker Unity HTTP Bridge** installed into your Unity Project

---

## 2. Unity Editor & AnkleBreaker Setup

Visora communicates with the Unity Editor over a lightweight local HTTP bridge provided by AnkleBreaker.

1. **Install AnkleBreaker**:
   - Import the AnkleBreaker package or place its Editor scripts inside your Unity project's `Assets/Plugins/` or `Assets/Editor/` directory.
2. **Start Unity Editor**:
   - Open your project in Unity Editor.
   - The AnkleBreaker bridge server starts automatically in background on port `7890` (or `7891` if 7890 is occupied).
3. **Verify Bridge**:
   - Open a browser or terminal and test the ping endpoint:
     ```bash
     curl http://127.0.0.1:7890/api/ping
     ```
   - Expected response: `{"status": "ok"}` or `{"pong": true}`.

---

## 3. Environment Configuration (`.env`)

Visora is configured using Pydantic Settings and supports `.env` files.

### Configuration Reference

Create a `.env` file in the project root based on [.env.example](file:///d:/Coding_projects/active/Visora/.env.example):

```bash
# Base URL of the Unity Editor HTTP bridge
UNITY_BRIDGE_URL=http://127.0.0.1

# Primary port (default for AnkleBreaker)
UNITY_BRIDGE_PORT=7890

# Secondary fallback port if primary is busy
UNITY_BRIDGE_FALLBACK_PORT=7891

# Full port scan range for multi-instance discovery (comma-separated)
UNITY_BRIDGE_PORTS_TO_SCAN=7890,7891,7892,7893

# Connection timeouts in seconds
UNITY_BRIDGE_TIMEOUT_SECONDS=10.0
UNITY_BRIDGE_PING_TIMEOUT_SECONDS=2.0

# Retry policy for resilient networking
UNITY_BRIDGE_MAX_RETRIES=2
UNITY_BRIDGE_RETRY_BACKOFF=0.5

# Server logging level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

---

## 4. Connecting MCP Clients

Visora runs as a standard Model Context Protocol (MCP) server over `stdio`.

### Claude Desktop

Add Visora to your `claude_desktop_config.json` (located at `%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "visora": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "d:/Coding_projects/active/Visora",
        "python",
        "-m",
        "backend.server"
      ]
    }
  }
}
```

---

### Cursor / Windsurf

In Cursor or Windsurf MCP settings (or `.cursor/mcp.json` / workspace configuration):

```json
{
  "mcpServers": {
    "visora": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "d:/Coding_projects/active/Visora",
        "python",
        "-m",
        "backend.server"
      ]
    }
  }
}
```

---

### Antigravity / OpenCode

Add to `.mcp.json` or `.opencode.json`:

```json
{
  "mcpServers": {
    "visora": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "d:/Coding_projects/active/Visora",
        "python",
        "-m",
        "backend.server"
      ],
      "type": "stdio"
    }
  }
}
```

---

### CLI / Standalone Mode

To start the MCP server manually for debugging or inspection:

```bash
# Run via uv
uv run python -m backend.server

# Or using the package entrypoint CLI
uv run visora
```

---

## 5. Bridge Health & Troubleshooting

### Diagnostic Tool: `unity_bridge_health`
If tools fail to reach Unity, ask the agent to call `unity_bridge_health`. It will scan all configured ports (`7890`, `7891`, `7892`, `7893`), test response latencies, and report the active bridge port.

### Common Issues & Resolutions

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| `BridgeUnreachableError` / Connection refused | Unity is not running or AnkleBreaker bridge is disabled. | Start Unity Editor with the project open. Verify port `7890` is listening (`netstat -an`). |
| Timeout on tool execution | Heavy operation or Unity is paused on breakpoint/modal dialog. | Ensure no modal dialogs (e.g. Unsaved Changes, Package Manager prompt) are open in Unity. |
| Compilation Lock Error | C# scripts in `Assets/` have syntax or compilation errors. | Call `unity_compilation_errors` to diagnose errors and fix the offending C# files before continuing. |
| Port mismatch | Unity instance opened on port `7891` instead of `7890`. | Visora will automatically fall back to `7891`. You can set `UNITY_BRIDGE_PORT=7891` in `.env` if desired. |
| Saving rejected | Attempted to save scene while in Play Mode. | Call `unity_play_mode` with `action: "stop"` first, then save. |
