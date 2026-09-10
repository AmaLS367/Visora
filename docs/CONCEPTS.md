# 💡 Concepts and Philosophy

> The design principles, architectural boundaries, and core philosophies that make Visora a dependable tool layer for autonomous Unity agents.

---

## 🎯 The Problem Visora Solves

Giving an AI agent raw access to arbitrary Unity Editor C# scripting creates capability, but not reliability. On every task, the agent is forced to independently resolve complex editor dynamics:

- ❓ Discover whether Unity is reachable, idle, or currently compiling scripts.
- ❓ Translate high-level intent into complex editor API calls and valid C#.
- ❓ Determine which camera or diagnostic view captures the necessary evidence.
- ❓ Preserve scene hierarchy, animation poses, and editor state while sampling or rendering.
- ❓ Disentangle network transport timeouts from compilation errors and domain reloads.
- ❓ Compress massive Unity JSON payloads into token-efficient context.
- ❓ Verify that a mutation actually succeeded rather than trusting a plain boolean flag.

These concerns are repetitive, stateful, and error-prone. Visora encapsulates them into **typed MCP tools** and **reproducible workflows**.

<p align="center">
  <img src="assets/concepts-workflow.jpg" alt="An intelligent observer inspects a camera, character rig, mesh, and animation timeline before a protected verified change" width="100%">
</p>
<p align="center"><em>Observation, controlled action, and verification form a single continuous loop — not disconnected steps.</em></p>

---

## ⚖️ Ad-Hoc Scripts vs. Visora Workflow

| Dimension | ⚠️ Traditional Ad-Hoc Scripting | ✨ Visora Typed MCP Workflow |
| :--- | :--- | :--- |
| **Agent Interface** | Guessing C# APIs & compiling strings | 46 validated, typed MCP tool contracts |
| **Diagnostics** | Grepping raw editor log output | Structured models with warnings & metrics |
| **Visual Verification** | Manual camera placement & screenshots | Multi-camera framing, viewport projection, and preview MP4s |
| **Scene Safety** | Risk of dirtying scenes or saving in Play Mode | Undo transactions, rollback groups, and Play Mode guards |
| **Animation QA** | Static screenshot or blind keyframe edits | Exact-time sampling, jerk detection, and IK contact solvers |
| **Token Economy** | Huge raw Unity JSON dumps | Compacted responses, schema pruning, and local disk artifacts |

---

## 🧩 The Product Model

Visora operates as a dedicated workflow layer between the MCP client and the live Unity Editor:

```text
🤖 Agent Intent
  └── 📐 Typed Visora Tool
        └── 🛡️ Safety & Capability Checks
              └── 🔌 Unity Bridge Operation (Native / Legacy)
                    └── 📊 Structured Interpretation
                          └── 👁️ Verifiable Evidence & Rollback Metadata
```

The Python backend manages agent vocabulary, parameter validation, orchestration, and token compaction. Unity remains the authoritative owner of scene, asset, and rendering state. The bridge serves purely as transport.

> [!NOTE]
> This separation ensures stability: *"Render the subject and verify framing"* remains a constant contract for the agent, regardless of whether it executes through a native C# endpoint or a legacy fallback bridge.

---

## 🧭 Core Philosophies

### 🔍 1. Evidence Over Optimistic Success

A return value of `success=true` indicates only that the operation completed without throwing an exception. It is **not** proof that a character animated properly, a mesh imported cleanly, or lighting rendered correctly. Visora pairs every action with verifiable evidence:
- 📦 **Asset Import** ➔ `inspect_imported_asset`
- 📐 **Camera Adjustments** ➔ Framing diagnostics, viewport projections, and screenshots
- 🎬 **Animation Changes** ➔ Temporal preview videos, jerk metrics, and contact analysis
- 🦴 **Rig Adjustments** ➔ Skeleton mapping and Avatar validation
- 🎨 **Visual Edits** ➔ Before/after comparison artifacts (`compare_screenshots`)

> [!TIP]
> Agents should always evaluate and report concrete evidence rather than passively echoing a success flag.

### 🩺 2. Diagnose Before Mutating

Many Unity symptoms stem from unrelated root causes. A black screenshot can signify missing scene lighting rather than missing geometry. A deformed character mesh may result from inverted bounds, mismatched root bones, invalid skin weights, or an incompatible clip. Mutating materials or transforms prematurely destroys vital diagnostic evidence.

Visora's canonical loop:
1. 🔍 **Inspect** bridge health and current editor state.
2. 🩺 **Diagnose** using the smallest check that isolates the root cause.
3. 🛡️ **Mutate** with a single scoped, recoverable transaction.
4. 👁️ **Verify** against the baseline using the same diagnostic.
5. ✅ **Retain** changes only when verifiable evidence confirms improvement.

### 📐 3. Typed Boundaries, Tolerant Interpretation

Public tool inputs and outputs are strictly typed with Pydantic models. Every result inherits from `BaseToolResult`, guaranteeing consistent fields for `success`, `error`, and retry metadata. 

However, external bridge payloads are parsed tolerantly. If an updated Unity service returns an unrecognized enum value, Visora emits a diagnostic warning and applies a safe fallback rather than crashing the agent's MCP session.

### 🛡️ 4. Scene State is a Finite Resource

Play Mode, animation sampling, temporary diagnostic cameras, render settings, scene dirty flags, and Undo stacks all represent mutable state. Every diagnostic tool must restore temporary state on both success and failure.

Visora explicitly separates:
- 👁️ **Inspection** from ⚡ **Mutation**
- ⏸️ **Edit Mode** from ▶️ **Play Mode**
- ↩️ **Undo Rollback** from 💾 **Disk Reload**
- 🎞️ **Temporary Preview State** from 💾 **Persisted Authoring**
- ⏱️ **Transport Timeouts** from ❌ **Execution Failures**

### ⚡ 5. High-Level Tools with Controlled Escape Hatches

Predefined, typed tools are inherently easier to validate, document, and test. While `safe_transaction` provides an escape hatch for arbitrary C# operations, high-level purpose-built tools should always be preferred for common workflows.

### 📉 6. Compact by Default

MCP tool definitions and output payloads consume context window space. Visora strips redundant schema descriptions, docstring clutter, and null JSON fields by default. Full Pydantic validation protects the implementation contract while keeping the wire footprint minimal.

---

## 👥 Who Benefits

- 🤖 **Autonomous Agents**: Gain explicit tools, predictable signatures, actionable error messages, retry hints, and visual artifacts.
- 🎮 **Unity Creators**: Receive transparent, auditable scene modifications with clear Undo stacks, preview videos, and operation logs.
- 🛠️ **Maintainers**: Enjoy a clean, modular architecture with strict separation between public MCP tools and Unity transport details.

---

## 🚫 What Visora Is Not

> [!WARNING]
> - **Not a Headless Replacement**: Visora controls an active Unity Editor instance; it is not a standalone game engine.
> - **Not an Open Remote Shell**: The bridge binds exclusively to loopback (`127.0.0.1`) and must never be exposed to untrusted networks.
> - **Not a Guarantee of Arbitrary C# Safety**: Untyped C# snippets executed through `safe_transaction` must register their own Undo operations.
> - **Not an Asset License Validator**: Search endpoints surface provider metadata, but compliance with licensing terms remains the user's responsibility.

---

## ⚖️ Intentional Architectural Tradeoffs

### 🎮 Live Editor vs. Headless Simulation
Visora prioritizes absolute fidelity to real Unity project state. This enables authentic camera renders, shader passes, and Avatar imports, while treating script compilation and domain reloads as standard lifecycle events.

### 💾 Local Disk Artifacts vs. Giant Base64 Payloads
Videos, high-resolution screenshots, and preview records are saved to the local `artifacts/` folder. Compact metadata and summaries are returned in the MCP response, preventing context window exhaustion while preserving full evidence on disk.

### 🚫 Zero Internal Python Compatibility Shims
Internal deprecated aliases accumulate tech debt and confuse agents. When an internal interface is refactored, all callers, imports, tests, and documentation are updated immediately to the canonical API.

---

## ✅ The Definition of "Done"

A Visora workflow task is considered fully complete when:

- [ ] 🎯 The requested operation returned `success=true` in its typed model.
- [ ] 🩺 Any diagnostic warnings or partial outcomes were evaluated.
- [ ] 👁️ Visual or structural evidence was verified against the expected state.
- [ ] 🔄 All temporary sampling poses, cameras, and preview state were restored.
- [ ] 💾 The scene was intentionally persisted (or cleanly rolled back).
- [ ] 💬 In case of failure, a concrete recovery action was communicated.

---

*Continue with [Agent Workflows](AGENT_WORKFLOWS.md) for practical recipes, or explore [Backend Architecture](backend/README.md) for system internals.*

