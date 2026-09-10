# Backend development

This guide covers local development of the Python MCP server and bundled Unity package. Read [Architecture](README.md) first if you are unfamiliar with the request lifecycle.

<p align="center">
  <img src="../assets/development-workflow.jpg" alt="Python and C-sharp source branches move through schemas, tests, compiler checks, Unity verification, documentation, and release" width="100%">
</p>
<p align="center"><em>Python and Unity changes have separate gates and converge only after verification.</em></p>

## Prerequisites

For Python work:

- Python 3.10 or newer;
- `uv`;
- Git.

For Unity package work:

- Unity 6 matching the package manifest;
- .NET SDK for the standalone C# compile/format gate;
- a locally licensed Unity Editor for EditMode integration tests.

## Environment setup

```bash
git clone https://github.com/AmaLS367/Visora.git
cd Visora
uv sync --locked --all-extras
cp .env.example .env
```

Use `uv` for every repository Python command. `uv.lock` is committed and CI checks that it is current.

Run the server:

```bash
uv run visora
```

or the equivalent module entrypoint:

```bash
uv run python -m backend.server
```

Because MCP uses stdio, manual terminal execution normally appears to wait for input. The useful first integration test is to start it from an MCP client and call `get_bridge_status`.

## Working tree rules

- Keep bridge HTTP details in `backend.bridge` or a narrow tool helper.
- Keep settings in `backend.config`; do not read new environment variables ad hoc.
- Use Pydantic models at public tool boundaries.
- Centralize reusable legacy C# in the relevant `scripts.py`.
- Return explicit unsupported or failure results; never return fake success.
- Bound diagnostic output and keep the default response compact.
- Preserve the scene and restore every temporary diagnostic state.
- Do not add internal Python compatibility aliases, wrappers, or deprecated import paths. Update all callers directly.
- Keep changes focused and use conventional commit messages.

## Common development paths

### Add or change an MCP tool

1. Identify the domain package and existing helper/bridge pattern.
2. Define or update the Pydantic result schema.
3. Implement the function with `@mcp.tool()` and an explicit return annotation.
4. Export it through the domain package so startup registration imports it.
5. Add tool-contract, domain, outage, and transport-shape tests as relevant.
6. Regenerate the catalog:

   ```bash
   uv run python scripts/render_tool_catalog.py
   ```

7. Update workflow and backend documentation.

### Add a native endpoint

1. Define the request DTO and route in `VisoraHttpRouter.cs`.
2. Dispatch Unity API work through `MainThreadDispatcher`.
3. Put domain logic in a focused service under `Editor/Services/`.
4. Advertise a named capability in `/api/visora/info`.
5. Add the Python `UnityBridge` method and make capability selection explicit.
6. Decide whether a legacy script fallback is equivalent; if not, fail clearly.
7. Classify replay behavior, especially read timeouts on mutations.
8. Add C# and Python tests, then run all Unity gates.

### Change a Python internal interface

Use one canonical name and signature. Update all imports, callers, tests, scripts, and documents in the same change. The project deliberately rejects compatibility shims inside Python; only the external AnkleBreaker HTTP/JSON transport retains backward compatibility.

## Validation by change type

Choose validation in proportion to the change.

### Documentation, comments, or other non-functional edits

Do not run test suites. Check only relevant documentation invariants, for example:

```bash
uv run python scripts/render_tool_catalog.py --check
```

Also inspect links, headings, version numbers, command examples, and the diff. CI intentionally ignores Markdown-only changes.

### Isolated Python tool change

Run formatting/linting/type checks on modified files and the narrow relevant tests. Example:

```bash
uv run ruff check backend/tools/vision/camera.py
uv run ruff format --check backend/tools/vision/camera.py
uv run mypy backend/tools/vision/camera.py
uv run pytest tests/unit/vision/test_vision.py
```

Adjust paths to the changed domain.

### Large Python or architectural change

Run the full Python gate sequentially:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run mypy .
uv run pytest
```

The first two commands can modify files. Review their diff before committing.

### Any Unity package change

After every change under `unity-package/`, compile against real Unity assemblies and verify C# formatting:

```bash
uv run python scripts/check_unity_package.py
uv run python scripts/check_unity_package.py --format
```

The script auto-discovers common Unity Hub paths. In a non-standard installation, set `VISORA_UNITY_MANAGED_DIR` to Unity’s `Editor/Data/Managed` directory.

After animation-stack changes, also run real Unity EditMode integration tests:

```bash
uv run python scripts/check_unity_tests.py
```

Set `VISORA_UNITY_EDITOR` when the Editor executable is not auto-discovered. Results and logs are written under ignored `artifacts/` paths.

## Test structure

```text
tests/unit/core/          config, MCP server, schemas, catalog, definitions
tests/unit/bridge/        transport and native authoring client behavior
tests/unit/vision/        images, cameras, capture, video
tests/unit/animation/     inspection, preview, records, authoring, IK, QA
tests/unit/mesh/          diagnostic analysis
tests/unit/asset/         providers, downloader, archives, import safety
tests/integration/        bridge, scene, assets, and multi-module workflow contracts
unity-package/Tests/     real Unity EditMode service tests
```

Tests must isolate `.env` when validating defaults because Pydantic settings load `.env` relative to the current working directory. Prefer injecting `Settings` into `UnityBridge` and patching the package-level bridge used by the domain under test.

## Generated tool catalog

The table between `GENERATED_TOOL_CATALOG_START` and `GENERATED_TOOL_CATALOG_END` in `docs/AGENT_WORKFLOWS.md` is generated from the actual MCP registry.

```bash
uv run python scripts/render_tool_catalog.py
uv run python scripts/render_tool_catalog.py --check
```

Never edit rows in that region by hand. Narrative workflow guidance around it remains authored documentation.

## Distribution checks

Project metadata and the console script live in `pyproject.toml`. Distribution metadata uses README as the long description; wheels include the `backend` package, `py.typed`, and the declared license file. Before a release or packaging change, build both artifacts, then use the repository validation script:

```bash
uv build
uv run python scripts/validate_distribution.py
```

Release version changes may need synchronized edits in Python package metadata, Docker image labels/tags, Unity package metadata, bridge response metadata, changelogs, and documentation. The Python distribution and Unity package have separate versions; do not assume they always advance together.

## Documentation checklist

When behavior changes, update the smallest relevant set:

- `README.md` for positioning, quick start, or headline capabilities;
- `docs/SETUP_GUIDE.md` for prerequisites, config, install, and recovery;
- `docs/AGENT_WORKFLOWS.md` for agent sequences and generated catalog;
- `docs/backend/BRIDGE.md` for transport/retry semantics;
- `docs/backend/TOOLS_AND_SCHEMAS.md` for public contracts;
- `docs/backend/STATE_AND_SAFETY.md` for mutation/restoration rules;
- `docs/backend/ASSET_PIPELINE.md` for network/file/import safety;
- `docs/CHANGELOG.md` and `docs/ROADMAP.md` for release history and scope.

Every command in documentation should be runnable from the repository root unless the surrounding text states otherwise.

## Debugging workflow

1. Reproduce with the narrowest public tool.
2. Record the typed result, including warnings and retry fields.
3. Confirm mode/port and editor state.
4. Determine whether the fault is MCP registration, tool preflight, HTTP transport, Unity routing/main-thread dispatch, domain service, or result parsing.
5. Add a regression at the lowest layer that proves the defect and a contract-level test when user-visible behavior changed.
6. Verify temporary state and artifacts after both the success and failure path.

See [Bridge](BRIDGE.md) for transport-specific diagnosis and [State and safety](STATE_AND_SAFETY.md) for recovery decisions.
