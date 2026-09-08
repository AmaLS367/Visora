from mcp.server import MCPServer

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
- Action and combat impacts must anchor hit-stop (set_keyframe_hold), camera recoil impulse, and \
events to a single authoritative impact timestamp; avoid unsynchronized procedural shake as default.
- Preflight Humanoid eligibility with validate_humanoid_avatar before retargeting mocap; if fatal \
blockers exist, never force Humanoid mode—use Generic Transform curves.
See docs/AGENT_WORKFLOWS.md and skills/ for the full tool catalog and workflow sequence."""

mcp = MCPServer("Visora", instructions=INSTRUCTIONS)
