import pytest

from backend import server
from backend.app import mcp


def test_main_starts_mcp_server(monkeypatch: pytest.MonkeyPatch) -> None:
    started = False

    def run() -> None:
        nonlocal started
        started = True

    monkeypatch.setattr(mcp, "run", run)

    server.main()

    assert started is True
