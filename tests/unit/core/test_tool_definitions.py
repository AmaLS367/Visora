import json
from typing import Any

import pytest
from mcp.server.mcpserver import Image
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import BaseModel

# Ensure all tools are registered on mcp
import backend.server
from backend.app import (
    VisoraMCPServer,
    _compact_json_schema,
    _compact_json_text,
    _compact_tool_description,
    _strip_none_values,
    mcp,
)
from backend.config import get_settings


def test_strip_none_values() -> None:
    data: dict[str, Any] = {
        "keep_str": "hello",
        "remove_none": None,
        "keep_zero": 0,
        "keep_false": False,
        "keep_empty_list": [],
        "nested": {
            "a": 1,
            "b": None,
            "items": [{"x": 10, "y": None}, None, "val"],
        },
    }
    cleaned = _strip_none_values(data)
    assert cleaned == {
        "keep_str": "hello",
        "keep_zero": 0,
        "keep_false": False,
        "keep_empty_list": [],
        "nested": {
            "a": 1,
            "items": [{"x": 10}, None, "val"],
        },
    }


def test_compact_json_text() -> None:
    # Valid JSON with newlines, spaces, nulls
    verbose_json = '{\n  "name": "test",\n  "optional": null,\n  "count": 42\n}'
    compact = _compact_json_text(verbose_json)
    assert compact == '{"name":"test","count":42}'
    assert "\n" not in compact

    # Plain text / error strings pass through untouched
    plain_text = "Error: something went wrong"
    assert _compact_json_text(plain_text) == plain_text

    # Invalid JSON starting with brace
    broken_json = "{not valid json}"
    assert _compact_json_text(broken_json) == broken_json


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


def test_compact_tool_description_handles_indented_docstring() -> None:
    doc = """
        Executes an atomic batch of animation clip modifications.

        Supported operations:
        - set_keyframe
        - move_keyframe

        Args:
            operations: List of operation dictionaries.
            transaction_id: Optional ID.

        Returns:
            AnimationTransactionResult.
    """
    compact = _compact_tool_description(doc)
    assert compact is not None
    assert "Executes an atomic batch of animation clip modifications." in compact
    assert "Supported operations:" in compact
    assert "Args:" not in compact
    assert "operations: List of operation dictionaries." not in compact
    assert "Returns:" not in compact


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
    assert len(tools) == 47

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
async def test_call_tool_compacts_results_by_default() -> None:
    # check_ticket_status returns a QueueStatusResult model
    result = await mcp.call_tool("check_ticket_status", {"ticket_id": "nonexistent-ticket-id"})
    assert isinstance(result, CallToolResult)
    # structured_content is stripped to prevent double serialization
    assert result.structured_content is None
    assert len(result.content) > 0

    text_block = result.content[0]
    assert hasattr(text_block, "text")
    # Result text must be single-line compact JSON
    assert "\n" not in text_block.text
    parsed = json.loads(text_block.text)
    assert parsed["ticket_id"] == "nonexistent-ticket-id"
    assert parsed["status"] == "error"
    # Verify that no None values exist in the deserialized object
    assert all(v is not None for v in parsed.values())
    # Verify specific optional fields that defaulted to None are omitted
    assert "duration_seconds" not in parsed
    assert "result" not in parsed


@pytest.mark.anyio
async def test_call_tool_results_toggle_preserves_structured_content(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "compact_tool_results", False)

    result = await mcp.call_tool("check_ticket_status", {"ticket_id": "nonexistent-ticket-id"})
    assert isinstance(result, CallToolResult)
    # When compacting is disabled, structured_content is retained
    assert result.structured_content is not None
    assert result.structured_content["ticket_id"] == "nonexistent-ticket-id"
    assert len(result.content) > 0
    # And text content has default indent=2
    text_block = result.content[0]
    assert hasattr(text_block, "text")
    assert "\n" in text_block.text


@pytest.mark.anyio
async def test_call_tool_multimodal_compacts_text_preserves_image() -> None:
    class DemoModel(BaseModel):
        status: str
        optional_note: str | None = None

    server = VisoraMCPServer("TestMultimodal")

    @server.tool()
    def sample_multimodal_tool() -> tuple[DemoModel, Image]:
        return (DemoModel(status="ok"), Image(data=b"fake_image_bytes", format="png"))

    res = await server.call_tool("sample_multimodal_tool", {})
    assert isinstance(res, CallToolResult)
    assert res.structured_content is None
    assert len(res.content) == 2
    assert isinstance(res.content[0], TextContent)
    assert isinstance(res.content[1], ImageContent)
    # TextContent is compacted without nulls or newlines
    assert res.content[0].text == '{"status":"ok"}'
    assert "\n" not in res.content[0].text
    # ImageContent is preserved
    assert res.content[1].data is not None
