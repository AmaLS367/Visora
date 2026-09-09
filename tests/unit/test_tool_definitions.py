import json
from typing import Any

import pytest
from mcp.types import CallToolResult

# Ensure all tools are registered on mcp
import backend.server
from backend.app import _compact_json_schema, _compact_tool_description, mcp
from backend.config import get_settings


def test_compact_tool_description_removes_parameter_and_return_blocks() -> None:
    doc = """Executes an atomic batch of animation clip modifications.

Supported operations:
- set_keyframe
- move_keyframe

Args:
    operations: List of operation dictionaries.
    transaction_id: Optional ID.

Returns:
    AnimationTransactionResult.

Raises:
    ValueError: If invalid.
"""
    compact = _compact_tool_description(doc)
    assert compact is not None
    assert "Executes an atomic batch of animation clip modifications." in compact
    assert "Supported operations:" in compact
    assert "Args:" not in compact
    assert "operations: List of operation dictionaries." not in compact
    assert "Returns:" not in compact
    assert "Raises:" not in compact


def test_compact_json_schema_strips_titles() -> None:
    schema: dict[str, Any] = {
        "title": "ToolArguments",
        "type": "object",
        "properties": {
            "path": {"title": "Path", "type": "string"},
            "nested": {
                "title": "NestedModel",
                "type": "object",
                "properties": {"val": {"title": "Val", "type": "integer"}},
            },
        },
    }
    cleaned = _compact_json_schema(schema)
    assert "title" not in cleaned
    assert "title" not in cleaned["properties"]["path"]
    assert "title" not in cleaned["properties"]["nested"]
    assert "title" not in cleaned["properties"]["nested"]["properties"]["val"]
    assert cleaned["properties"]["path"]["type"] == "string"


@pytest.mark.anyio
async def test_list_tools_compacted_by_default() -> None:
    tools = await mcp.list_tools()
    assert len(tools) >= 50

    # 1. Output schema must be None for all tools
    for tool in tools:
        assert tool.output_schema is None, f"Tool {tool.name} still has output_schema"

    # 2. Descriptions should not duplicate Args: or Returns: sections
    for tool in tools:
        assert tool.description, f"Tool {tool.name} has empty description"
        assert "\nArgs:" not in tool.description, f"Tool {tool.name} contains Args: in description"
        assert "Args:\n" not in tool.description, f"Tool {tool.name} contains Args: in description"
        assert "\nReturns:" not in tool.description, f"Tool {tool.name} contains Returns: in description"

    # 3. Payload size check (< 60,000 characters)
    tools_dict = [t.model_dump(by_alias=True, exclude_none=True) for t in tools]
    payload_str = json.dumps(tools_dict)
    assert len(payload_str) < 60_000, f"Payload size {len(payload_str)} exceeds 60KB limit"


@pytest.mark.anyio
async def test_compact_tool_definitions_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "compact_tool_definitions", False)

    tools = await mcp.list_tools()
    # When compacting is disabled, tools with structured return types have output_schema
    tools_with_output = [t for t in tools if t.output_schema is not None]
    assert len(tools_with_output) > 0


@pytest.mark.anyio
async def test_call_tool_maintains_structured_content() -> None:
    # check_ticket_status is a lightweight bridge tool that validates arguments and returns structured model
    result = await mcp.call_tool("check_ticket_status", {"ticket_id": "nonexistent-ticket-id"})
    assert isinstance(result, CallToolResult)
    assert result.structured_content is not None
    assert "ticket_id" in result.structured_content
    assert result.structured_content["ticket_id"] == "nonexistent-ticket-id"
    assert len(result.content) > 0
