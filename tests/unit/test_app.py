from backend.app import mcp


def test_mcp_server_has_asset_workflow_instructions() -> None:
    """Regression test: the MCP `instructions` field is what reaches every connecting client with
    no per-project setup (unlike a copied Claude Code skill file), so the sharpest gotchas found
    live in this codebase's history - Sketchfab's search being unreliable and glTF needing an
    importer package - must stay surfaced here, not just in a skill file nobody copied in.
    """
    assert mcp.instructions
    assert "web_search_assets" in mcp.instructions
    assert "gltf" in mcp.instructions.lower()
    assert "inspect_imported_asset" in mcp.instructions
