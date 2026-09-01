<p align="center">
  <img src="docs/assets/banner.png" alt="Visora Banner" width="100%">
</p>

# Visora 👁️

Visora is a high-level Model Context Protocol (MCP) server wrapper designed to interface with the Unity Editor via an HTTP bridge (AnkleBreaker plugin). It exposes specialized tools for Unity scene manipulation, screenshot capturing, world-to-screen projections, skinned mesh diagnostics, animation inspections, and async task execution queueing.

## 🚀 Stack

- **Python 3.10+**
- **FastMCP (mcp)** — MCP server framework
- **HTTPX** — Async HTTP client for communication with Unity
- **Pydantic v2 + pydantic-settings** — Typed config, data validation, and tool output schemas
- **Asyncio** — Asynchronous task loop & ticket polling

---

## 📂 Project Structure

```
visora/
├── backend/
│   ├── __init__.py
│   ├── server.py          # MCP server entrypoint
│   ├── bridge.py          # HTTP client to AnkleBreaker
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── vision.py      # screenshot, project_world_points
│   │   ├── animation.py   # clip inspector, skeleton mapper
│   │   ├── scene.py       # safe transaction, playmode management
│   │   ├── mesh.py        # skinned mesh diagnostics
│   │   └── queue.py       # long-running ticket system
│   └── schemas/
│       └── __init__.py    # pydantic models for all tool outputs
├── pyproject.toml
├── README.md
└── .env.example           # UNITY_BRIDGE_URL, UNITY_BRIDGE_PORT
```

---

## 🔧 Features & Requirements

### 1. Port Fallback Mechanism (`bridge.py`)
The HTTP bridge client automatically detects and handles port fallback. It tries port `7890` first (the default port of the AnkleBreaker bridge), and if connection fails or times out, it gracefully falls back to port `7891`.

### 2. Async Ticket Polling (`tools/queue.py`)
A custom queue ticket polling tool allows waiting for long-running operations in the Unity Editor. It polls `/api/queue/status` asynchronously using a specified timeout and polling interval, preventing blockage of the primary MCP event loop.

### 3. High-Quality Schema Integration (`schemas/__init__.py`)
Every tool is strictly typed, and its output is validated using Pydantic models. This ensures robust communication and auto-documentation under the Model Context Protocol.

---

## 🛠️ Getting Started

### Installation
You can manage the project and its dependencies using `uv` or `pip`:

```bash
# Using uv (highly recommended)
uv pip install -e .

# Or using pip
pip install -e .
```

### Environment Configuration
Copy the `.env.example` file to `.env` and adjust the variables:

```bash
cp .env.example .env
```

### Running the MCP Server
To run the server locally:

```bash
uv run python -m backend.server
```

---

## 🔗 AnkleBreaker API Endpoints Wrapped
- `GET /api/ping`
- `POST /api/editor/execute-code`
- `POST /api/editor/play-mode`
- `POST /api/scene/save`
- `GET /api/compilation/errors`
- `GET /api/queue/status`
