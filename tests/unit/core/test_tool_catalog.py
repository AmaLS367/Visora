import subprocess
import sys


def test_documented_tool_catalog_matches_registered_mcp_server_tools() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/render_tool_catalog.py", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
