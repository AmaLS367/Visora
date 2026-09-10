# 📚 Visora Documentation Hub

> Complete architectural, operational, and development documentation for Visora — bridging AI agents with Unity Editor through typed MCP workflows.

This directory documents Visora from three complementary perspectives: the **operator** setting it up, the **autonomous agent** executing workflows, and the **maintainer** extending tools and bridges.

<p align="center">
  <img src="assets/system-architecture.jpg" alt="An AI agent communicates through typed Python tools and a resilient bridge with a live Unity Editor" width="100%">
</p>
<p align="center"><em>One agent-facing workflow layer, two bridge implementations, and Unity as the authoritative source of truth.</em></p>

---

## 🧭 Choose Your Starting Point

| Objective | Guide | Focus Area |
| :--- | :--- | :--- |
| 💡 **Understand Core Concepts** | [Concepts and Philosophy](CONCEPTS.md) | Problem formulation, design principles, benefits, and boundaries. |
| 🛠️ **Install & Connect Client** | [Setup Guide](SETUP_GUIDE.md) | Local environment, MCP clients (Claude/Cursor), Docker, and verification. |
| 🤖 **Agent Workflows & Recipes** | [Agent Workflows](AGENT_WORKFLOWS.md) | Complete 47-tool MCP catalog and task-specific recipes. |
| 🏗️ **Backend Architecture** | [Backend Architecture](backend/README.md) | Process boundaries, startup, dispatch, and request lifecycles. |
| 🌐 **Bridge Transport & Retries** | [Bridge & Failure Semantics](backend/BRIDGE.md) | Native/legacy routing, domain-reload recovery, and error codes. |
| 📐 **Tools & Result Schemas** | [Tools and Schemas](backend/TOOLS_AND_SCHEMAS.md) | Pydantic contracts, result compaction, and tool authoring. |
| 🛡️ **Scene Integrity & Undo** | [State and Safety](backend/STATE_AND_SAFETY.md) | Edit/Play mode boundaries, transactions, and state restoration. |
| 📦 **Asset Ingestion Pipeline** | [Asset Pipeline](backend/ASSET_PIPELINE.md) | Quarantine sandboxing, SSRF defenses, archive checks, and imports. |
| 💻 **Maintainer Workflow** | [Backend Development](backend/DEVELOPMENT.md) | Local development, test suites, and pre-commit validation gates. |
| 🗺️ **Releases & Roadmap** | [Changelog](CHANGELOG.md) & [Roadmap](ROADMAP.md) | Released features, version milestones, and future plans. |

---

## 🗺️ Documentation Map

### 👤 User & Operator Documentation

- 🛠️ [Setup Guide](SETUP_GUIDE.md) — Supported runtime combinations, installation options, MCP client configuration, environment settings, and Docker containerization.
- 🩺 [Troubleshooting](SETUP_GUIDE.md#troubleshooting) — Observable symptom resolutions (e.g. *bridge unreachable*, *Unity domain reload busy*, *imported model empty*).

### 🤖 Agent & Product Documentation

- 💡 [Concepts and Philosophy](CONCEPTS.md) — Explains why Visora is a safety workflow layer rather than an ad-hoc C# snippet runner.
- 🤖 [Agent Workflows](AGENT_WORKFLOWS.md) — Task-oriented guide featuring the verified 47-tool MCP catalog.
- 🗺️ [Roadmap](ROADMAP.md) & 📜 [Changelog](CHANGELOG.md) — Release histories and planned evolution.

### 🏗️ Maintainer & Architecture Documentation

The [`backend/`](backend/) directory details deep implementation mechanics:
- ⚡ **Startup & Discovery**: Import-time tool registration and multi-port bridge discovery.
- 🔄 **Failure Recovery**: Distinguishing transport timeouts from Unity script compilation or domain reloads.
- 📦 **Pydantic Contracts**: Strict public typing paired with tolerant transport parsing.
- 🛡️ **Transactional Safety**: Scoped undo groups, Play Mode guards, and temporary state cleanup.
- 🔒 **Security Defense**: Asset quarantine, path traversal guards, SSRF validation, and zip bomb mitigations.

---

## 📌 Sources of Truth

When documentation and implementation diverge, resolve discrepancies using this strict hierarchy:

1. 📐 **Tool Signatures & Schemas**: `backend/tools/` and `backend/schemas/`.
2. 🔌 **Bridge Protocols**: `backend/bridge/` and `unity-package/Editor/Core/VisoraHttpRouter.cs`.
3. 🧪 **Automated Test Suites**: Tests under `tests/` and `unity-package/Tests/Editor/`.
4. 📋 **Generated Catalog**: The tool table in [Agent Workflows](AGENT_WORKFLOWS.md#tool-catalog).
5. 📖 **Narrative Documentation**.

> [!NOTE]
> Version requirements are defined in `pyproject.toml` and `unity-package/package.json`. Configuration defaults are defined in `backend/config.py`, with `.env.example` as the canonical reference.

---

## 🎨 Visual Language & Design System

Documentation graphics adhere to the visual identity established by the Visora banner:
- 🌌 **Near-black technical canvas**
- 🔷 **Cyan** (`#00FFFF` / `#38BDF8`) for observation, inspection, and telemetry paths
- 🟣 **Violet** (`#A855F7` / `#8B5CF6`) for mutations, kinematic solvers, and recovery paths
- ⚪ **Pure white / neutral gray** for verification accents and boundaries

Project illustrations and generative prompt definitions reside under [`docs/assets/`](assets/README.md).

---

## 🔄 Keeping Documentation Synchronized

> [!IMPORTANT]
> Documentation is part of Visora's public tool contract. Whenever modifying tool names, parameters, result structures, or safety invariants, always update the corresponding documentation.

After modifying tool definitions, synchronize and verify the generated catalog:

```bash
uv run python scripts/render_tool_catalog.py
uv run python scripts/render_tool_catalog.py --check
```

> [!TIP]
> For documentation-only changes, do not run the entire Python/Unity test suite. Verify Markdown links, headings, generated regions, and formatting instead. See [Backend Development](backend/DEVELOPMENT.md#validation-by-change-type).

