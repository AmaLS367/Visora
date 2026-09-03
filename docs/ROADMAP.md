# Visora — Roadmap

> **Current Release:** 🚀 **v0.1.2 (Completed)**<br>
> **Next Target:** 🔮 **TBD**

---

## 🚀 Released in v0.1.2 — Open-Source & Packaging Foundation

### 1. ⚖️ Apache-2.0 Licensing
* **Status:** ✅ Completed
* **Scope:** Added the complete Apache License 2.0 text, SPDX package metadata, and a distributed license file so the reuse and redistribution terms are explicit for all consumers.

### 2. 🤝 Contribution & Community Health
* **Status:** ✅ Completed
* **Scope:** Added structured GitHub issue forms for bugs, feature requests, and questions; a security-aware issue chooser; a PR template; contributor guidance; a security policy; a code of conduct; and support guidance.

### 3. 📦 First-Class PyPI Metadata
* **Status:** ✅ Completed
* **Scope:** Polished `pyproject.toml` with authorship, discovery keywords, Python/platform classifiers, SPDX licensing, and canonical links to source, documentation, issue tracker, and changelog so PyPI presents Visora as a complete package.

### 4. 🧩 Typed & Installable Distribution
* **Status:** ✅ Completed
* **Scope:** Published the PEP 561 `py.typed` marker and improved the PyPI-rendered README with absolute links, an install command, and a concise MCP/Unity bridge quickstart.

### 5. ✅ Distribution Integrity Gates
* **Status:** ✅ Completed
* **Scope:** Extended CI to validate built package metadata and assert that released distributions include legal and typing artifacts before publishing.

---

## 🚀 Released in v0.1.1

### 1. 🌐 Asset Web Search & Auto-Download for Unity
* **Status:** ✅ Completed
* **Scope:** Provide agents with tools to perform web searches and automatically download 3D models, environments, rigs, textures, and props directly into the active Unity project. This empowers AI agents to autonomously discover and import required 3D assets to animate rich, context-complete scenes.
* **Security hardening:** Downloads now use HTTPS-only public-host validation, external quarantine staging, strict format/archive limits, collision-safe names, and verified Unity import results. Sketchfab IDs can be resolved directly by the import tool.

### 2. ⚙️ Production CI/CD (GitHub Actions)
* **Status:** ✅ Completed
* **Scope:** Create a polished, multi-stage GitHub Actions workflow suite covering code formatting (`ruff format`), strict linting (`ruff check`), static typing (`mypy`), automated unit and integration tests (`pytest`), and tag-triggered PyPI/GitHub release publishing.

### 3. 🐳 Polished Docker Support
* **Status:** ✅ Completed
* **Scope:** Delivered a hardened, multi-stage `Dockerfile` and Compose configuration for running Visora as a containerized headless MCP server. The image has a minimal runtime stage, an immutable non-editable Python environment, a dedicated non-root user, bytecode compilation, cache-efficient locked dependency installation, and a restrictive default Compose sandbox with configurable Unity bridge access.

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
