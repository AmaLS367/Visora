# Tools and schemas

Visora’s public API is its MCP tool surface. Python modules and Unity endpoints are implementation details; tool names, arguments, result fields, errors, warnings, and evidence paths are what agents depend on.

<p align="center">
  <img src="../assets/typed-contracts.jpg" alt="Irregular Unity, HTTP, image, and diagnostic payloads pass through typed validation into compact result cards" width="100%">
</p>
<p align="center"><em>Transport complexity is normalized into a small, predictable agent-facing contract.</em></p>

## Tool families

| Family | Python package | Responsibilities |
| --- | --- | --- |
| Bridge and queue | `backend.tools.bridge` | Connectivity, port scan, editor task tickets |
| Scene | `backend.tools.scene` | Editor state, Play Mode, save policy, generic safe transactions, restore |
| Vision | `backend.tools.vision` | Cameras, screenshots, viewport projection, framing, video, visual comparison |
| Animation | `backend.tools.animation` | Clips, skeletons, previews, records, authoring transactions, Humanoid, contacts, IK, gaze, QA |
| Mesh | `backend.tools.mesh` | Skinned-mesh inspection and diagnostic classification |
| Asset | `backend.tools.asset` | Search, secure download/import, local import, inspection, instantiation |

The complete parameter table is generated in [Agent workflows](../AGENT_WORKFLOWS.md#tool-catalog). Do not maintain a second hand-written catalog.

## Registration model

A public tool is an async function decorated with the singleton server:

```python
from backend.app import mcp
from backend.schemas import SomeResult


@mcp.tool()
async def some_operation(required_value: str, limit: int = 10) -> SomeResult: ...
```

Registration happens when Python imports the module. To make a new tool reachable:

1. Put it in the narrow domain module under `backend/tools/`.
2. Import and export it from that domain package’s `__init__.py`.
3. Ensure `backend.server` imports the domain package.
4. Add its result model to `backend/schemas/` and schema exports.
5. Add it to the contract tests and domain tests.
6. Regenerate the tool catalog.

Do not create a second MCP server instance or register the same function through multiple import paths.

## Input contract

The MCP framework derives JSON Schema from the function signature. Public parameters should therefore be:

- typed explicitly;
- named for agent intent, not bridge DTO field names;
- bounded or validated before expensive work;
- supplied with safe defaults;
- documented with effects and units in the function docstring.

Use Pydantic models or constrained literals when an input has structure. Avoid accepting an opaque raw dictionary when the fields form a durable public vocabulary.

Validation should happen at the narrowest correct layer:

- MCP/Pydantic: shape and types;
- tool function: domain combinations and safe ranges;
- bridge client: transport behavior;
- Unity service: authoritative existence and editor-state checks.

## Output contract

Every registered tool must explicitly return a `BaseToolResult` subtype, or a tuple whose first item is one. The tuple form is used when the MCP response also includes an image block.

The common envelope is:

| Field | Meaning |
| --- | --- |
| `success` | Whether the represented operation completed |
| `error` | Concrete failure reason, otherwise null/omitted on the compact wire |
| `retryable` | Whether the identical call is worth retrying after Unity settles |
| `unity_state` | `compiling`, `updating`, `reloading`, or an internal state description |
| `retry_after_seconds` | Suggested delay before a transient retry |

Domain schemas add compact facts, warnings, counts, issue categories, paths, and messages. Prefer useful summaries and bounded samples over raw bridge dumps.

### `success` is not visual proof

A tool may successfully import an asset that still needs project-specific material setup, or capture a valid image in which a subject is out of frame. Results should expose the evidence needed for the next decision, and workflow documentation should name the verification call.

### Warnings are part of the contract

Warnings describe degraded but usable results: truncated diagnostic arrays, unsupported auto-framing, a suffixed destination name, an unresolved curve path, or pose restoration that Unity did not confirm. Do not hide these in logs.

## Parsing bridge payloads

Native and legacy responses have related but not always identical shapes. Keep that normalization close to the tool domain:

- use shared `_extract_result_payload`-style helpers instead of open-coding wrapper checks;
- unwrap the legacy executor’s outer `{success, result, logs}` before evaluating the operation result;
- accept documented alternate key casing only at the external HTTP boundary;
- coerce unknown external enum-like values to an explicit fallback plus warning when the underlying operation remains useful;
- cap arrays using configured diagnostic limits before constructing the result.

Do not add Python compatibility aliases or preserve deprecated internal identifiers. External HTTP/JSON compatibility with AnkleBreaker is the only backward-compatibility exception.

## Native capability plus legacy fallback

For a workflow supported by both transports, the normal call pattern is:

```python
payload = await bridge.execute_capability(
    legacy_script(...),
    native_path="/api/visora/domain/operation",
    native_payload={...},
    retry_on_timeout=False,  # for non-idempotent writes
)
```

The bridge chooses the route. Tools should not duplicate port or flavor logic.

Some workflows are genuinely native-only because the legacy executor cannot reproduce their timing or atomicity. Those tools must return an explicit unsupported-capability failure. They must never return fake success or silently perform a weaker mutation.

## Error handling

At the tool boundary:

```python
try:
    payload = await domain_pkg.bridge.execute_capability(...)
except Exception as exc:
    return SomeResult(**bridge_error(exc), warnings=[...])
```

Use narrower exception sets internally where recovery behavior differs. Preserve Unity compilation errors, runtime errors, HTTP status, and actionable messages. Do not collapse every failure into “bridge error.”

For `BridgeBusyError`, use `bridge_error()` or `bridge_retry_fields()` so retry metadata survives. Never infer retryability from matching text.

## MCP context compaction

`VisoraMCPServer` reduces context overhead in two places.

### Tool definitions

With `COMPACT_TOOL_DEFINITIONS=true` (default):

- output schemas are omitted from the advertised tool definition;
- long docstring sections beginning with Args/Parameters/Returns/Raises are removed from the description;
- redundant JSON Schema `title` fields are removed recursively.

The Python annotations and Pydantic result models still exist and are tested. Compaction changes what is advertised to the model, not the implementation contract.

### Tool results

With `COMPACT_TOOL_RESULTS=true` (default):

- duplicate MCP `structured_content` is removed;
- JSON text is re-serialized compactly;
- null-valued fields are omitted recursively.

Image blocks remain available for visual tools. Full artifacts remain on disk even when inline content is downscaled.

Disable either setting while debugging schema or serialization behavior, understanding that this increases MCP context usage.

## Adding a tool: design checklist

Before implementation:

- Can an existing tool express the workflow without arbitrary C#?
- Is the operation inspection, diagnosis, mutation, or verification?
- What Unity state is required?
- What temporary state must be restored?
- Is replay after a timeout safe?
- Is the operation supported by legacy, native, or both?
- What result fields let an agent decide the next action?

During implementation:

- centralize config in `backend.config`;
- centralize bridge behavior in `backend.bridge`;
- centralize reusable legacy C# in the domain `scripts.py`;
- use a typed result model;
- bound large results;
- preserve warnings and concrete errors;
- use an operation ID or other idempotency mechanism for mutations where supported;
- return artifact paths for large visual outputs.

Before completion:

- test success, Unity-declared failure, bridge outage, and transient-busy behavior as applicable;
- test native and legacy shapes when both are supported;
- verify restoration on success and exception;
- regenerate `docs/AGENT_WORKFLOWS.md` with `scripts/render_tool_catalog.py`;
- update the relevant workflow and backend document.

See [Development](DEVELOPMENT.md) for validation commands and [State and safety](STATE_AND_SAFETY.md) for mutation-specific requirements.
