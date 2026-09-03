# Visora — Roadmap

> **Current Release:** 🚀 **v0.1.0 (Completed)**  
> **Next Target:** 🔮 **v0.1.1 (Planned)**

---

## 🔮 Planned for v0.1.1

### 1. 🌐 Asset Web Search & Auto-Download for Unity
* **Status:** ✅ Completed
* **Scope:** Provide agents with tools to perform web searches and automatically download 3D models, environments, rigs, textures, and props directly into the active Unity project. This empowers AI agents to autonomously discover and import required 3D assets to animate rich, context-complete scenes.
* **Security hardening:** Downloads now use HTTPS-only public-host validation, external quarantine staging, strict format/archive limits, collision-safe names, and verified Unity import results. Sketchfab IDs can be resolved directly by the import tool.

### 2. ⚙️ Production CI/CD (GitHub Actions)
* **Status:** ✅ Completed
* **Scope:** Create a polished, multi-stage GitHub Actions workflow suite covering code formatting (`ruff format`), strict linting (`ruff check`), static typing (`mypy`), automated unit and integration tests (`pytest`), and tag-triggered PyPI/GitHub release publishing.

### 3. 🐳 Polished Docker Support
* **Status:** ⏳ Planned
* **Scope:** Deliver a hardened, multi-stage `Dockerfile` and `docker-compose` configuration optimized for running Visora as a containerized headless MCP server with minimal image size, secure non-root execution, and configurable bridge network pass-through.

---

## 🚀 Completed Milestones (v0.1.0)

### 1. 👁️ Visual Scene Understanding
* **Status:** ✅ Completed
* **Scope:** Agents can inspect the Unity scene through camera screenshots, compare visual changes, and diagnose rendering or layout problems directly instead of relying solely on logs.

### 2. 📐 Camera-Aware Verification
* **Status:** ✅ Completed
* **Scope:** Agents can render from any scene camera, project 3D world points and transforms into 2D viewport coordinates, and identify off-screen objects, clipping planes, depth errors, or framing issues.

### 3. 🛡️ Safe Unity Scene Operations
* **Status:** ✅ Completed
* **Scope:** Agents can execute editor actions without corrupting the scene: cleanly manage Play Mode / Edit Mode lifecycles, await Unity idle states, enforce safe-save policies, and rollback temporary state.

### 4. 🎞️ Animation Inspection & Sampling
* **Status:** ✅ Completed
* **Scope:** Agents can inspect `AnimationClip` curves and bindings, detect unintended translation/scale drift, sample poses at exact timestamps, and verify keyframe evaluations.

### 5. 🦴 Skeleton & Rig Intelligence
* **Status:** ✅ Completed
* **Scope:** Agents can inspect imported hierarchies, resolve bones via exact and fuzzy matching, identify duplicate or helper bones, and understand complex rigs (such as MMD primary/D-bone chains).

### 6. 🧶 Skinned Mesh Diagnostics
* **Status:** ✅ Completed
* **Scope:** Agents can diagnose mesh deformation anomalies, abnormal bounding boxes, broken bone bindings, and submesh/material mismatches, distinguishing rigging issues from material defects.

### 7. 🔌 Reliable Unity Bridge Layer
* **Status:** ✅ Completed
* **Scope:** Visora provides a resilient high-level MCP bridge layer with automatic multi-port discovery, async ticket/queue polling, structured exception handling, and health probes.

### 8. 📦 Structured Tool Outputs
* **Status:** ✅ Completed
* **Scope:** Every Visora tool returns compact, strongly typed Pydantic models designed for LLM reasoning rather than unstructured console dumps or uninformative success flags.

### 9. 📚 Agent Workflow Documentation
* **Status:** ✅ Completed
* **Scope:** Comprehensive guides covering setup instructions, agent diagnostic recipes, client configurations (Claude Desktop, Cursor, Antigravity, OpenCode), and safety protocols.

### 10. 🧪 Production Test Coverage
* **Status:** ✅ Completed
* **Scope:** Full test suite covering configuration, bridge transport, queue polling, scene transactions, tool output schemas, and mocked Unity responses to prevent regressions.

### 11. 📦 Dedicated Visora Unity Package
* **Status:** ✅ Completed
* **Scope:** Native Unity companion package alongside AnkleBreaker support for custom camera rendering, editor coroutines, persistent diagnostics, and stable custom endpoints.
