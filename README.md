<p align="center">
  <img src="https://raw.githubusercontent.com/AmaLS367/Visora/master/docs/assets/banner.png" alt="Visora Banner" width="100%">
</p>

# Visora 👁️

Visora is a high-level Model Context Protocol (MCP) server for Unity Editor. It supports AnkleBreaker as the default compatibility transport and the bundled native Unity package, with typed tools for visual diagnostics, safe scene work, animation, rigging, meshes, and queue polling.

---

## 📚 Documentation

- 📖 **[Agent Workflow Guide & Practical Recipes](https://github.com/AmaLS367/Visora/blob/master/docs/AGENT_WORKFLOWS.md)** — Step-by-step diagnostic recipes, camera projections, rig/animation debugging, and agent safety rules.
- ⚙️ **[Setup & Integration Guide](https://github.com/AmaLS367/Visora/blob/master/docs/SETUP_GUIDE.md)** — Setup instructions for Unity Editor, AnkleBreaker, `.env` config, and client setups (Claude Desktop, Cursor, Antigravity, OpenCode).
- 🗺️ **[Roadmap & Progress](https://github.com/AmaLS367/Visora/blob/master/docs/ROADMAP.md)** — Current status and milestones.
- 📝 **[Changelog](https://github.com/AmaLS367/Visora/blob/master/docs/CHANGELOG.md)** — Release history and version notes.

---

## 🚀 Stack

- **Python 3.10+**
- **MCPServer (mcp)** — MCP server framework
- **HTTPX** — Async HTTP client with automatic port discovery and retry backoff
- **Pydantic v2 + pydantic-settings** — Typed config, validation, and structured tool output schemas
- **Asyncio** — Asynchronous task loop & non-blocking ticket polling

---

## 📂 Project Structure

```
visora/
├── backend/
│   ├── __init__.py
│   ├── app.py             # MCPServer application instance
│   ├── server.py          # MCP server entrypoint
│   ├── config.py          # Centralized Pydantic settings
│   ├── bridge.py          # HTTP bridge client with multi-port failover
│   ├── tools/
│   │   ├── vision/        # screenshots, camera rendering, viewport projection, video
│   │   ├── animation/     # clip curve inspection, skeleton mapping, pose sampling
│   │   ├── scene/         # safe transactions, playmode lifecycle, compilation check
│   │   ├── mesh/          # skinned mesh diagnostics, bone binding & bound audit
│   │   └── bridge/        # health check, port scan, queue ticket polling
│   └── schemas/           # Pydantic output models for every tool
├── docs/
│   ├── AGENT_WORKFLOWS.md # Agent recipes, workflows, and safety rules
│   ├── SETUP_GUIDE.md     # Installation and MCP client configuration
│   └── ROADMAP.md         # Roadmap & feature matrix
├── tests/                 # Unit and integration test suites
├── Dockerfile              # Hardened production container image
├── compose.yaml            # Secure local MCP container configuration
├── pyproject.toml
└── .env.example
```

---

## 🛠️ Getting Started

### Install from PyPI

```bash
pip install visora
visora
```

Visora starts an MCP server over standard input/output. Keep a Unity Editor open with either AnkleBreaker or the bundled `com.visora.editor` package configured as its HTTP bridge; see the [setup guide](https://github.com/AmaLS367/Visora/blob/master/docs/SETUP_GUIDE.md).

### Development Installation

```bash
# Using uv (recommended)
uv pip install -e .

# Or using pip
pip install -e .
```

### Environment Configuration

Copy the `.env.example` file to `.env`:

```bash
cp .env.example .env
```

### Running the MCP Server

```bash
# Direct module execution
uv run python -m backend.server

# Or package CLI
uv run visora
```

### Docker

Visora's container uses stdio, just like a local MCP server. Build and run it with Docker Compose:

```bash
docker compose build --pull
docker compose run --rm -i visora
```

The Compose service reaches a Unity bridge on the host through `host.docker.internal`; configure bridge and optional provider variables in `.env`. See the [Docker setup guide](docs/SETUP_GUIDE.md#docker) for Linux networking and security details.

---

## 🧰 Available MCP Tools

The generated, source-of-truth list of all 24 registered tools and their current parameters is in the [Agent Workflow Guide](https://github.com/AmaLS367/Visora/blob/master/docs/AGENT_WORKFLOWS.md#tool-catalog).

---

## License

Copyright 2026 Ama.

Licensed under the [Apache License, Version 2.0](LICENSE).
