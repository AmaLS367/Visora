# Concepts and philosophy

## The problem Visora solves

Giving an AI agent access to arbitrary Unity Editor scripting creates capability, but not reliability. The agent still has to solve several different problems on every task:

- discover whether Unity is reachable and ready;
- translate intent into editor APIs and compilable C#;
- decide which camera or diagnostic view contains evidence;
- preserve scene, animation, and editor state while sampling or rendering;
- distinguish transport failure from compilation failure and domain reload;
- compress large Unity responses into information useful to another model;
- prove that a change worked rather than trusting a boolean.

Those concerns are repetitive, stateful, and easy to get subtly wrong. Visora captures them once as typed MCP tools and reusable workflows.

<p align="center">
  <img src="assets/concepts-workflow.jpg" alt="An intelligent observer inspects a camera, character rig, mesh, and animation timeline before a protected verified change" width="100%">
</p>
<p align="center"><em>Observation, controlled action, and verification are one loop—not separate features.</em></p>

## The product model

Visora is a workflow layer between an MCP client and a live Unity Editor:

```text
agent intent
  -> typed Visora tool
  -> safety and capability checks
  -> Unity bridge operation
  -> structured interpretation
  -> evidence and recovery metadata
```

The Python backend owns the agent-facing vocabulary, validation, orchestration, and compact result shape. Unity owns authoritative editor state and performs Unity API calls. The bridge is transport, not the product abstraction exposed to the agent.

This separation matters. “Render the subject and report whether it is framed” is a stable agent operation. The implementation may use a native endpoint today or a compatible C# executor on another bridge without changing the agent’s goal or result model.

## Core philosophy

### Evidence over optimistic success

`success=true` only says that the operation represented by a result completed. It is not proof that the scene looks correct, a character moves, or an imported asset contains a mesh. Visora workflows therefore pair actions with evidence:

- asset import with `inspect_imported_asset`;
- camera changes with framing diagnostics, viewport projection, or screenshots;
- animation edits with temporal preview and motion metrics;
- rig changes with skeleton or Avatar validation;
- visual changes with comparison artifacts.

An agent should report the evidence it observed, not merely repeat a success flag.

### Diagnose before mutating

Many Unity symptoms have several unrelated causes. A dark screenshot can mean missing lights rather than missing geometry. A deformed model can mean bad bounds, a wrong root bone, invalid weights, or an incompatible animation. Changing materials or transforms before classifying the problem destroys useful evidence and can make the scene harder to recover.

Visora’s preferred loop is:

1. Inspect bridge and editor state.
2. Gather the smallest diagnostic that separates likely causes.
3. Make one scoped, recoverable change.
4. Re-run the same diagnostic or create a comparable artifact.
5. Keep the change only when the evidence improves.

### Typed boundaries, tolerant interpretation

Inputs and outputs are typed with Pydantic. Every tool result inherits a common contract with `success`, `error`, and retry metadata. This gives the agent a predictable envelope even when the underlying bridge differs.

Unity and legacy bridge payloads are still external data. Parsers preserve useful success when a newer Unity service returns an unknown enum-like value: the value becomes an explicit fallback with a warning instead of causing an unrelated validation crash. Strictness belongs at the public boundary; tolerance belongs at the transport interpretation boundary.

### Scene state is a resource

Play Mode, animation sampling, temporary cameras, render settings, active scenes, dirty flags, Undo groups, and asset imports are all state. Every diagnostic operation must own the state it changes and restore it on both success and failure.

This is why Visora distinguishes:

- inspection from mutation;
- Edit Mode from Play Mode;
- Undo rollback from disk reload;
- temporary preview state from persisted authoring;
- a transport timeout from a known failed operation.

### Prefer high-level operations, retain a controlled escape hatch

Named tools are easier to validate, document, test, and reason about than arbitrary code. They should cover common workflows. `safe_transaction` remains available for editor operations that do not yet deserve a dedicated tool, but arbitrary C# is not treated as equivalent to a purpose-built capability.

### Compact by default

MCP tool definitions and results share an agent’s context window with the task itself. Visora removes redundant schema titles, long docstring sections, duplicate structured content, and null JSON fields by default. Full Pydantic models remain the implementation contract; the wire representation is optimized for reasoning cost.

## Who benefits

### Agents

Agents get explicit tools, deterministic parameter names, actionable errors, retry hints, and visual outputs they can inspect directly. They spend less context inventing bridge scripts and less time recovering from editor state mistakes.

### Unity users

Users get changes that are easier to audit and reproduce. Visual artifacts, preview records, concrete warnings, Undo groups, and operation IDs make an agent’s work legible instead of opaque.

### Maintainers

Maintainers get a stable public MCP vocabulary over replaceable transport details. The same tool contract can route to a native endpoint or a legacy-compatible executor, while shared schemas and tests enforce behavior across modules.

## What Visora is not

- It is not a replacement for the Unity Editor or Unity’s renderer.
- It is not a general remote shell and should not expose the native bridge to untrusted networks.
- It is not a guarantee that arbitrary C# is safe or undoable.
- It is not a visual foundation model; it creates and structures visual evidence for the connected agent.
- It is not an asset-license validator. Search results expose provider metadata, but the user remains responsible for license compliance.
- It is not fully transport-independent internally. The current backend deliberately targets the AnkleBreaker-compatible HTTP/JSON contract and the bundled native package.

## Intentional tradeoffs

### A live Editor instead of headless simulation

Visora chooses fidelity to real project state over an isolated model of Unity. This enables real renders, imports, Avatar checks, and editor lifecycle handling, but requires the correct project to be open and makes domain reload a normal operating condition.

### Local artifacts instead of giant inline payloads

Screenshots, contact sheets, MP4s, and preview records are written under `artifacts/`. Tools may also return selected image content, but large binary payloads are excluded unless explicitly requested. This keeps MCP responses usable while preserving full-fidelity evidence on disk.

### Capability negotiation instead of version guesses

The native package advertises feature names. The backend checks those capabilities before choosing optimized paths because bridge flavor or version alone cannot prove endpoint semantics. If capability discovery fails transiently, Visora avoids permanently caching a false negative.

### No internal Python compatibility layers

Internal aliases and deprecated wrappers accumulate ambiguity for agents and maintainers. Visora updates all Python callers, imports, tests, and docs when an internal interface changes. Compatibility is maintained only at the external HTTP/JSON boundary where existing Unity bridges require it.

## The definition of “done”

A Visora task is complete when:

- the requested operation returned a typed successful result;
- warnings and partial outcomes were examined;
- the relevant visual or structural evidence was checked;
- temporary editor state was restored;
- the intended persistence decision was explicit;
- failures, when present, were reported with a concrete next action.

For practical sequences that implement this philosophy, continue with [Agent workflows](AGENT_WORKFLOWS.md). For implementation details, see [Backend architecture](backend/README.md).
