from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, InputRequiredResult, TextContent
from mcp.types import Tool as MCPTool

from backend.config import get_settings

# The MCP `instructions` field is sent to every connecting client as part of its own context, with
# no per-project setup required (unlike a Claude Code skill file, which only applies if a user
# copies it into their own project). Kept focused on asset, animation, and camera gotchas that live
# in live Unity testing - see docs/AGENT_WORKFLOWS.md and skills/ for the full detail.
INSTRUCTIONS = """Visora controls a Unity Editor over an HTTP bridge. Key workflow rules:
- search_assets's Sketchfab results are unreliable for a specific/named model: Sketchfab's own \
search API ignores the query text (verified live - a nonsense query returns the same results as \
a real one). For a specific model, call web_search_assets instead and use the sketchfab:<uid> it \
returns as asset_id.
- .gltf/.glb (Sketchfab's default export format) needs a glTF importer package (e.g. \
com.unity.cloud.gltfast) installed in the target Unity project - vanilla Unity has no built-in \
one. download_and_import_asset fails explicitly if it's missing, rather than importing nothing.
- After download_and_import_asset reports success, call inspect_imported_asset before trusting \
the result: asset_type should be a real type with submesh_count > 0, not an empty placeholder.
- Never infer animation or retargeting success from a static screenshot: verify motion over time \
via preview_animation (checking motion_summary.is_static) using the smallest safe preview first.
- Action and combat impacts must anchor hit-stop (via edit_animation_transaction operation \
set_keyframe_hold), camera recoil impulse, and events (via create_event) to a single authoritative \
impact timestamp; avoid unsynchronized procedural shake as default.
- Preflight Humanoid eligibility with validate_humanoid_avatar before retargeting mocap; if fatal \
blockers exist, never force Humanoid mode—use Generic Transform curves.
See docs/AGENT_WORKFLOWS.md and skills/ for the full tool catalog and workflow sequence."""

_SECTION_MARKERS = (
    "\nArgs:\n",
    "\nParameters:\n",
    "\nReturns:\n",
    "\nRaises:\n",
    "\nArgs:",
    "\nParameters:",
    "\nReturns:",
    "\nRaises:",
)


def _compact_tool_description(description: str | None) -> str | None:
    if not description:
        return description
    desc = description
    for marker in _SECTION_MARKERS:
        if marker in desc:
            desc = desc.split(marker)[0]
    return desc.strip()


def _compact_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "title":
            continue
        if isinstance(value, dict):
            cleaned[key] = _compact_json_schema(value)
        elif isinstance(value, list):
            cleaned[key] = [_compact_json_schema(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def _strip_none_values(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_none_values(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none_values(v) for v in obj]
    return obj


def _compact_json_text(text: str) -> str:
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")) and not (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        return text
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return text
    cleaned = _strip_none_values(parsed)
    return json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)


class VisoraMCPServer(MCPServer):
    """MCP server wrapper that compacts tool definitions and results to minimize LLM context window overhead."""

    async def list_tools(self) -> list[MCPTool]:
        tools = await super().list_tools()
        settings = get_settings()
        if not settings.compact_tool_definitions:
            return tools

        for tool in tools:
            tool.output_schema = None
            tool.description = _compact_tool_description(tool.description)
            if tool.input_schema:
                tool.input_schema = _compact_json_schema(tool.input_schema)
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context[Any, Any] | None = None,
    ) -> CallToolResult | InputRequiredResult:
        result = await super().call_tool(name, arguments, context)
        settings = get_settings()
        if not settings.compact_tool_results:
            return result

        if isinstance(result, CallToolResult):
            result.structured_content = None
            for block in result.content:
                if isinstance(block, TextContent) and block.text:
                    block.text = _compact_json_text(block.text)
        return result


mcp = VisoraMCPServer("Visora", instructions=INSTRUCTIONS)
