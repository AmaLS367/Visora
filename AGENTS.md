## Project Context: Visora

Visora is a high-level MCP server for Unity agents. Its job is to let AI agents work with Unity scenes through reliable, typed tools instead of ad hoc Unity Editor scripting and raw logs.

The product exists because low-level Unity bridge access is not enough for real agent work. Agents need to see what the camera sees, inspect scene state, diagnose rigs/animations/meshes, and verify changes safely. Visora should turn those workflows into explicit MCP tools.

### Product Goal

Build an agent-facing Unity workflow layer that helps agents:

- visually inspect Unity scenes through camera renders and screenshots;
- project world points and transforms into camera viewport space;
- safely execute editor operations without corrupting scenes;
- inspect AnimationClips, skeletons, skinned meshes, and Unity errors;
- distinguish visual/rendering issues from geometry, rigging, or animation issues;
- return compact structured data that agents can reason about.

### Architecture Direction

The first version is a Python MCP wrapper over the existing AnkleBreaker Unity HTTP bridge.

Current transport target:

- Unity Editor runs the AnkleBreaker bridge.
- Visora talks to it over HTTP.
- Visora exposes higher-level MCP tools to agents.

Do not start by building a custom Unity package unless the current bridge becomes a concrete limitation. The near-term priority is the Python MCP layer: schemas, tool behavior, bridge reliability, and verification workflows.

### Repository Shape

- Project/distribution name: `visora`.
- Runtime package code currently lives under `backend/`.
- MCP entrypoint: `backend.server:main`.
- CLI command: `uv run visora`.
- Config lives in `backend.config` and should remain centralized through Pydantic settings.
- Tool modules live in `backend/tools/`.
- Output schemas live in `backend/schemas/`.
- Roadmap lives in `docs/ROADMAP.md`.

### Engineering Rules

- Use `uv` for all Python commands.
- Prefer typed Pydantic models at tool boundaries.
- Keep Unity bridge API details inside `backend.bridge` or narrow tool helpers.
- Do not duplicate raw C# snippets across tools; centralize reusable Unity code when it appears.
- Do not return fake success from unimplemented tools. Return real results or explicit not-implemented errors.
- Do not silently hide Unity bridge failures. Report unreachable bridge, timeout, HTTP errors, and Unity execution errors clearly.
- Keep tools agent-friendly: compact result, concrete fields, clear warnings, no giant raw dumps by default.
- Preserve scene safety: do not save during Play Mode, do not leave temporary sampling/render state behind, and restore Unity state after diagnostic operations.
- Prefer small focused commits and conventional commit messages.
- **Strictly NO internal backward compatibility in Python:** There is zero tolerance for backward compatibility layers, legacy aliases, compatibility wrappers, or preserving deprecated identifiers/imports inside the Python codebase. The ONLY backward compatibility allowed anywhere in this project is the external HTTP/JSON transport protocol with the Unity Editor's AnkleBreaker bridge. When code, modules, functions, or signatures are refactored, moved, or renamed, all callers, imports, and tests MUST be updated directly to the new canonical interface. Never introduce compatibility shims.
- **Strict passive mode on questions/discussion:** When the user asks questions, points out something, or discusses code/architecture, ONLY answer the question. NEVER modify files, rename files, or trigger code changes unless the user explicitly gives a direct command to do so.

### Code Validation Guidelines (Pre-commit Gates)

To optimize development speed and resource usage, follow these validation rules:

1. **Non-functional edits & Micro-changes (e.g., comments, docstrings, typing hints in docs, typos, prompt updates, variable/file renames):** If a change does not alter runtime code logic or type signatures, **NEVER run tests or full test suites**.
2. **Isolated changes affecting tools (e.g., typing a variable, local helper tweak):** Run linting/typing gates **only on the modified files** to be token-efficient.
3. **Large-scale changes (e.g., new test files, core logic additions, architectural refactoring):** Perform a full validation gate.

#### Running a Full Validation Gate

Execute the following commands sequentially to clean, format, typecheck, and test the entire repository:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run mypy .
uv run pytest
```

<!-- code-review-graph MCP tools -->

## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool                          | Use when                                               |
| ----------------------------- | ------------------------------------------------------ |
| `detect_changes`            | Reviewing code changes — gives risk-scored analysis   |
| `get_review_context`        | Need source snippets for review — token-efficient     |
| `get_impact_radius`         | Understanding blast radius of a change                 |
| `get_affected_flows`        | Finding which execution paths are impacted             |
| `query_graph`               | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes`     | Finding functions/classes by name or keyword           |
| `get_architecture_overview` | Understanding high-level codebase structure            |
| `refactor_tool`             | Planning renames, finding dead code                    |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
