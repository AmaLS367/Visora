# Visora documentation

This directory documents Visora from three points of view: the person installing it, the agent using it, and the maintainer extending it.

<p align="center">
  <img src="assets/system-architecture.jpg" alt="An AI agent communicates through typed Python tools and a resilient bridge with a live Unity Editor" width="100%">
</p>
<p align="center"><em>One agent-facing workflow layer, two bridge implementations, and Unity as the source of truth.</em></p>

## Choose a starting point

| I want to… | Read |
| --- | --- |
| Understand the idea and product boundaries | [Concepts and philosophy](CONCEPTS.md) |
| Install Visora and connect an MCP client | [Setup guide](SETUP_GUIDE.md) |
| See every MCP tool and reliable task recipes | [Agent workflows](AGENT_WORKFLOWS.md) |
| Understand the Python and Unity architecture | [Backend architecture](backend/README.md) |
| Diagnose bridge discovery, reloads, or timeouts | [Bridge and failure semantics](backend/BRIDGE.md) |
| Add or modify a tool or result model | [Tools and schemas](backend/TOOLS_AND_SCHEMAS.md) |
| Reason about Undo, saving, Play Mode, and cleanup | [State and safety](backend/STATE_AND_SAFETY.md) |
| Understand secure asset downloads and imports | [Asset pipeline](backend/ASSET_PIPELINE.md) |
| Set up a development environment and validate changes | [Backend development](backend/DEVELOPMENT.md) |
| Check what shipped or what is next | [Changelog](CHANGELOG.md) and [roadmap](ROADMAP.md) |

## Documentation map

### User and operator documentation

- [Setup guide](SETUP_GUIDE.md) covers supported runtime combinations, installation, MCP configuration, environment variables, Docker, and first-run verification.
- [Agent workflows](AGENT_WORKFLOWS.md) is task-oriented. Its tool table is generated from the actual MCP registry and must not be edited by hand.
- [Troubleshooting](SETUP_GUIDE.md#troubleshooting) starts from observable symptoms such as “bridge unreachable,” “Unity is busy,” or “the imported model is empty.”

### Product documentation

- [Concepts and philosophy](CONCEPTS.md) explains why Visora is a workflow layer rather than a collection of editor-script snippets.
- [Roadmap](ROADMAP.md) records release scope and historical delivery notes.
- [Changelog](CHANGELOG.md) records changes by release.

### Maintainer documentation

The [`backend/`](backend/) section describes implementation details that are easy to miss when reading one tool in isolation:

- process startup and import-time tool registration;
- the distinction between MCP transport and Unity HTTP transport;
- bridge flavor and capability negotiation;
- why read timeouts are not automatically replayed;
- how domain reload is recognized and recovered;
- Pydantic result invariants and context compaction;
- scene/animation safety and temporary-state ownership;
- asset quarantine, path containment, redirect validation, and import verification;
- Python, C#, Unity, and generated-document validation gates.

## Sources of truth

When documents and implementation disagree, use these sources in order:

1. Tool signatures and Pydantic schemas under `backend/tools/` and `backend/schemas/`.
2. Bridge behavior in `backend/bridge/` and native routes in `unity-package/Editor/Core/VisoraHttpRouter.cs`.
3. Automated tests under `tests/` and `unity-package/Tests/Editor/`.
4. Generated tool catalog in [Agent workflows](AGENT_WORKFLOWS.md#tool-catalog).
5. Narrative documentation.

Version requirements come from `pyproject.toml` and `unity-package/package.json`. Configuration defaults come from `backend/config.py`; `.env.example` is the copyable reference.

## Visual language

Documentation illustrations follow the visual identity established by the Visora banner: near-black technical space, cyan request/inspection paths, violet mutation/recovery paths, and white verification accents.

Keep future additions consistent:

- use conceptual raster illustrations for orientation and mood;
- use Mermaid or tables when exact labels and relationships matter;
- avoid embedding explanatory text inside generated images;
- write alt text that explains the relationship shown, not just the objects present;
- add a short caption stating the page’s key idea;
- optimize large raster files before committing them;
- reuse an illustration only when the same concept is genuinely being explained.

Current project illustrations and their reusable prompt set live under [`docs/assets/`](assets/README.md).

## Keeping documentation current

Documentation is part of the public tool contract. A change is incomplete when it changes a tool name, parameter, output, feature requirement, failure mode, installation step, or safety rule without updating the relevant guide.

After changing an MCP tool, regenerate and verify the catalog:

```bash
uv run python scripts/render_tool_catalog.py
uv run python scripts/render_tool_catalog.py --check
```

For documentation-only edits, do not run the Python or Unity test suites. Check Markdown links, headings, generated regions, and factual consistency instead. See [Backend development](backend/DEVELOPMENT.md#validation-by-change-type).
