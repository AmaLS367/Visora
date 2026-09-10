# 📐 Tools and Schemas Architecture

> Design principles for Visora's public Model Context Protocol (MCP) surface, Pydantic data modeling, error mapping, and context window compaction.

Visora's public product boundary is its MCP tool registry. While Python modules and Unity C# endpoints implement the underlying logic, AI agents interact exclusively through tool names, parameter schemas, typed results, and diagnostic evidence artifacts.

<p align="center">
  <img src="../assets/typed-contracts.jpg" alt="Irregular Unity, HTTP, image, and diagnostic payloads pass through typed validation into compact result cards" width="100%">
</p>
<p align="center"><em>Transport complexity is normalized into a predictable, compact, agent-facing contract.</em></p>

---

## 🗂️ MCP Tool Families

The 47 registered MCP tools are partitioned into focused domain packages:

| Family | Python Package | Core Responsibilities |
| :--- | :--- | :--- |
| 🔌 **Bridge & Queue** | `backend.tools.bridge` | Connectivity, multi-port scanning, long-running task status |
| 🎮 **Scene & Play Mode** | `backend.tools.scene` | Editor state, Play Mode transitions, atomic Undo transactions |
| 👁️ **Vision & Rendering** | `backend.tools.vision` | Cameras, screenshots, viewport projections, video capture, diffs |
| 🎬 **Animation & Kinematics** | `backend.tools.animation` | Clips, skeletons, previews, IK solvers, gaze, contact baking, QA |
| 📐 **Mesh Diagnostics** | `backend.tools.mesh` | Skinned mesh inspection and deformation issue classification |
| 📦 **Asset Pipeline** | `backend.tools.asset` | 3D search, quarantine downloads, Unity import, instantiation |
| 🧩 **Prefab Assets** | `backend.tools.prefab` | Read-only Prefab, Variant, and nested Prefab asset inspection |

> [!NOTE]
> The full parameter inventory is automatically maintained in [Agent Workflows](../AGENT_WORKFLOWS.md#tool-catalog).

---

## 🏷️ Registration & Discovery Model

Every public MCP tool is an `async` function decorated with the singleton server instance:

```python
from backend.app import mcp
from backend.schemas import SomeResult


@mcp.tool()
async def some_operation(required_value: str, limit: int = 10) -> SomeResult: ...
```

### 📋 Steps to Register a New Tool

1. Implement the tool in a specialized module under `backend/tools/<domain>/`.
2. Import and expose the function in `backend/tools/<domain>/__init__.py`.
3. Verify that `backend.server` imports the domain package.
4. Define the output model in `backend/schemas/` and expose it in `backend/schemas/__init__.py`.
5. Add unit and contract tests under `tests/unit/`.
6. Run `uv run python scripts/render_tool_catalog.py` to synchronize documentation.

---

## 📥 Input Contract & Validation Layering

JSON Schema is derived automatically by the MCP framework from Python function type hints. Parameter design principles:
- 🎯 **Explicit Typing**: Use primitive types (`str`, `int`, `float`, `bool`) or Pydantic models. Avoid opaque unstructured `dict` inputs.
- 💬 **Intent-Driven Naming**: Name arguments for agent intent (e.g. `subject_path`), not low-level Unity C# DTO field names.
- 🛡️ **Defensive Bounds**: Provide sensible defaults and enforce upper bounds (e.g. maximum frame count, dimensions) before triggering expensive operations.
- 📖 **Clear Docstrings**: Document expected physical units (meters, seconds, degrees) and scene side-effects.

### 🧱 Multi-Layered Validation Architecture

```text
1. 📐 MCP / Pydantic Layer ➔ Validates types, ranges, required fields
2. 🛠️ Tool Preflight Layer ➔ Validates domain logic (Edit Mode, path existence)
3. 🔌 Bridge Client Layer   ➔ Validates HTTP connection & transport status
4. 🎮 Unity Service Layer   ➔ Authoritative validation on Unity main thread
```

---

## 📤 Output Contract & Status Envelopes

Every tool returns a model derived from `BaseToolResult`:

| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | `bool` | Whether the requested operation completed successfully |
| `error` | `str \| None` | Actionable failure message (omitted when null in compact wire format) |
| `retryable` | `bool` | Indicates whether re-invoking after Unity settles is recommended |
| `unity_state` | `str \| None` | Transient state: `compiling`, `updating`, `reloading`, etc. |
| `retry_after_seconds` | `float \| None` | Recommended backoff wait before retrying |

> [!CAUTION]
> **`success=true` is NOT Visual Proof!** An asset import can return `success=true` while missing custom shader assignments. Always verify outcome evidence via secondary diagnostics or visual inspections.

---

## 🔄 Normalizing Bridge Payloads

Native and legacy bridge responses exhibit subtle structural differences. Tools normalize payloads using shared helpers:
- Unwrap outer legacy execution wrappers (`{success, result, logs}`) cleanly.
- Coerce unknown bridge enum strings to safe defaults using `coerce_literal()` and emit diagnostic warnings.
- Enforce diagnostic array limits (`DIAGNOSTIC_MAX_*`) before constructing output models.
- **Strictly No Internal Compatibility Shims**: Internal Python code uses canonical APIs directly.

---

## ⚡ Dual-Transport Dispatching Pattern

For workflows supporting both native and legacy bridges:

```python
payload = await bridge.execute_capability(
    legacy_script(...),
    native_path="/api/visora/domain/operation",
    native_payload={...},
    retry_on_timeout=False,  # for non-idempotent writes
)
```

> [!IMPORTANT]
> Genuinely native-only workflows (such as hardware-timed animation recording or atomic multi-key transactions) must explicitly return an unsupported capability error when run against a legacy bridge, rather than faking success.

---

## 🛡️ Error Handling & Exception Mapping

```python
try:
    payload = await domain_pkg.bridge.execute_capability(...)
except Exception as exc:
    return SomeResult(**bridge_error(exc), warnings=[...])
```

- Always preserve compiler diagnostics, stack traces, and HTTP status codes.
- Map `BridgeBusyError` via `bridge_error(exc)` to ensure `retryable=true` and `retry_after_seconds` propagate to the agent.

---

## 📉 MCP Context Window Compaction

To preserve context window tokens for LLM reasoning, `VisoraMCPServer` implements automated compaction:

### 1. Tool Definition Compaction (`COMPACT_TOOL_DEFINITIONS=true`)
- Strips redundant JSON Schema `title` attributes recursively.
- Truncates verbose `Args:`, `Returns:`, and `Raises:` sections from docstrings.
- Excludes duplicate output schemas from initial tool announcements.

### 2. Result Payload Compaction (`COMPACT_TOOL_RESULTS=true`)
- Strips redundant duplicate `structured_content` blocks.
- Recursively removes `null` / `None` fields from serialized JSON.
- Minifies whitespace while keeping disk artifacts in `artifacts/` at full fidelity.

---

## ✅ New Tool Authoring Checklist

Before declaring a new tool complete:
- [ ] 🎯 **Purpose**: Does this replace ad-hoc C# with a typed, repeatable workflow?
- [ ] 🛡️ **Safety**: Does it restore temporary state on both success and failure?
- [ ] ⏱️ **Idempotency**: Is `retry_on_timeout=False` specified for mutating writes?
- [ ] 🔌 **Transport**: Does it support native, legacy, or declare native-only capability requirements?
- [ ] 📐 **Schemas**: Does the output model inherit from `BaseToolResult`?
- [ ] 🧪 **Testing**: Are unit tests and contract tests written and passing?
- [ ] 📋 **Catalog**: Was `uv run python scripts/render_tool_catalog.py` executed?

