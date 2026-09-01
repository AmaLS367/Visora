"""Render or verify the MCP tool catalog embedded in the workflow documentation."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from backend.app import mcp
from backend.tools import animation, bridge, mesh, scene, vision

CATALOG_START = "<!-- GENERATED_TOOL_CATALOG_START -->"
CATALOG_END = "<!-- GENERATED_TOOL_CATALOG_END -->"
WORKFLOW_PATH = Path("docs/AGENT_WORKFLOWS.md")


def render_catalog() -> str:
    """Return a deterministic Markdown table from FastMCP's registered tool metadata."""
    rows = ["| Tool | Parameters | Result |", "| --- | --- | --- |"]
    for tool in sorted(mcp._tool_manager._tools.values(), key=lambda item: item.name):
        properties = tool.parameters.get("properties", {})
        required = set(tool.parameters.get("required", []))
        parameters = ", ".join(f"`{name}`{'*' if name in required else ''}" for name in properties) or "—"
        output_model = tool.fn_metadata.output_model
        result = output_model.__name__ if output_model is not None else "BaseToolResult"
        rows.append(f"| `{tool.name}` | {parameters} | `{result}` |")
    return "\n".join(rows)


def document_with_catalog(document: str, catalog: str) -> str:
    """Replace exactly the generated catalog region, preserving the surrounding authored guidance."""
    pattern = rf"{re.escape(CATALOG_START)}.*?{re.escape(CATALOG_END)}"
    replacement = f"{CATALOG_START}\n{catalog}\n{CATALOG_END}"
    updated, replacements = re.subn(pattern, replacement, document, flags=re.DOTALL)
    if replacements != 1:
        raise ValueError("docs/AGENT_WORKFLOWS.md must contain exactly one generated catalog region")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail when the committed catalog is stale")
    args = parser.parse_args()

    document = WORKFLOW_PATH.read_text(encoding="utf-8")
    expected = document_with_catalog(document, render_catalog())
    if args.check:
        if document != expected:
            print("docs/AGENT_WORKFLOWS.md tool catalog is stale; run scripts/render_tool_catalog.py")
            return 1
        return 0

    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
