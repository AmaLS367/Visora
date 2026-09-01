from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.bridge import (
    BridgeConnectionError,
    BridgeError,
    BridgeHTTPError,
    BridgeTimeoutError,
    UnityBridge,
)
from backend.config import Settings
from backend.tools.bridge.health import get_bridge_status
from backend.tools.bridge.queue import check_ticket_status, wait_for_ticket


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        unity_bridge_url="http://127.0.0.1",
        unity_bridge_port=7890,
        unity_bridge_fallback_port=7891,
        unity_bridge_ports_to_scan=[7890, 7891, 7892, 7893],
        unity_bridge_timeout_seconds=5.0,
        unity_bridge_ping_timeout_seconds=1.0,
        unity_bridge_max_retries=2,
        unity_bridge_retry_backoff=0.01,
    )


@pytest.mark.anyio
async def test_candidate_ports_ordering(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    assert bridge.candidate_ports == [7890, 7891, 7892, 7893]


@pytest.mark.anyio
async def test_get_active_port_default_success(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    mock_req = httpx.Request("GET", "http://127.0.0.1:7890/api/ping")
    mock_resp = httpx.Response(200, json={"status": "ok"}, request=mock_req)
    with patch.object(bridge.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        port = await bridge.get_active_port()
        assert port == 7890
        assert bridge._active_port == 7890
        mock_get.assert_called_once_with("http://127.0.0.1:7890/api/ping", timeout=1.0)


@pytest.mark.anyio
async def test_get_active_port_fallback(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    def side_effect(url: str, **kwargs: Any) -> httpx.Response:
        req = httpx.Request("GET", url)
        if ":7890" in url:
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(200, json={"status": "ok"}, request=req)

    with patch.object(bridge.client, "get", side_effect=side_effect):
        port = await bridge.get_active_port()
        assert port == 7891
        assert bridge._active_port == 7891


@pytest.mark.anyio
async def test_get_active_port_all_failed(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    with patch.object(bridge.client, "get", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(BridgeConnectionError) as excinfo:
            await bridge.get_active_port()
        assert excinfo.value.ports == [7890, 7891, 7892, 7893]


@pytest.mark.anyio
async def test_scan_available_ports(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    def side_effect(url: str, **kwargs: Any) -> httpx.Response:
        req = httpx.Request("GET", url)
        if ":7890" in url:
            return httpx.Response(200, json={"status": "ok"}, request=req)
        raise httpx.ConnectError("Port closed")

    with patch.object(bridge.client, "get", side_effect=side_effect):
        results = await bridge.scan_available_ports()
        assert len(results) == 4
        assert results[0]["port"] == 7890
        assert results[0]["is_open"] is True
        assert results[0]["latency_ms"] is not None
        assert results[1]["port"] == 7891
        assert results[1]["is_open"] is False
        assert results[1]["latency_ms"] is None


@pytest.mark.anyio
async def test_ping_success_and_failure(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    mock_req = httpx.Request("GET", "http://127.0.0.1:7890/api/ping")
    with patch.object(bridge.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json={"status": "ok"}, request=mock_req)
        ok, latency = await bridge.ping(port=7890)
        assert ok is True
        assert latency is not None

        mock_get.side_effect = httpx.ConnectError("Connection refused")
        ok, latency = await bridge.ping(port=7890)
        assert ok is False
        assert latency is None


@pytest.mark.anyio
async def test_request_retry_and_cache_invalidation(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890

    # First request on port 7890 fails with ConnectError, then get_active_port detects 7891, and retry succeeds
    calls = []

    async def mock_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        req = httpx.Request(method, url)
        if ":7890" in url:
            raise httpx.ConnectError("Connection dropped")
        return httpx.Response(200, json={"result": "success"}, request=req)

    async def mock_get(url: str, **kwargs: Any) -> httpx.Response:
        req = httpx.Request("GET", url)
        if ":7890" in url:
            raise httpx.ConnectError("7890 down")
        return httpx.Response(200, json={"status": "ok"}, request=req)

    with (
        patch.object(bridge.client, "request", side_effect=mock_request),
        patch.object(bridge.client, "get", side_effect=mock_get),
    ):
        resp = await bridge._request("POST", "/api/scene/save")
        assert resp.status_code == 200
        assert resp.json() == {"result": "success"}
        assert bridge._active_port == 7891


@pytest.mark.anyio
async def test_request_http_error(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890

    request = httpx.Request("POST", "http://127.0.0.1:7890/api/editor/execute-code")
    err_resp = httpx.Response(500, request=request, text="Script compilation failed")

    with patch.object(bridge.client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = err_resp
        with pytest.raises(BridgeHTTPError) as excinfo:
            await bridge._request("POST", "/api/editor/execute-code")
        assert excinfo.value.status_code == 500
        assert "Script compilation failed" in excinfo.value.message


@pytest.mark.anyio
async def test_request_timeout_error(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890

    ping_req = httpx.Request("GET", "http://127.0.0.1:7890/api/ping")
    ping_resp = httpx.Response(200, json={"status": "ok"}, request=ping_req)

    with (
        patch.object(bridge.client, "request", side_effect=httpx.ReadTimeout("Timeout")),
        patch.object(bridge.client, "get", return_value=ping_resp),
    ):
        with pytest.raises(BridgeTimeoutError) as excinfo:
            await bridge._request("POST", "/api/editor/execute-code")
        assert excinfo.value.timeout_seconds == 5.0


@pytest.mark.anyio
async def test_async_context_manager(mock_settings: Settings) -> None:
    async with UnityBridge(settings=mock_settings) as bridge:
        assert isinstance(bridge, UnityBridge)
        assert not bridge.client.is_closed
    assert bridge.client.is_closed


# ==============================================================================
# MCP Tool Tests
# ==============================================================================


@pytest.mark.anyio
async def test_get_bridge_status_connected() -> None:
    with (
        patch("backend.tools.bridge.health.bridge.scan_available_ports", new_callable=AsyncMock) as mock_scan,
        patch("backend.tools.bridge.health.bridge.ping", new_callable=AsyncMock) as mock_ping,
        patch("backend.tools.bridge.health.bridge.get_active_port", new_callable=AsyncMock) as mock_port,
        patch("backend.tools.bridge.health.bridge.get_editor_state", new_callable=AsyncMock) as mock_state,
    ):
        mock_scan.return_value = [
            {"port": 7890, "is_open": True, "latency_ms": 1.2},
            {"port": 7891, "is_open": False, "latency_ms": None},
        ]
        mock_ping.return_value = (True, 1.2)
        mock_port.return_value = 7890
        mock_state.return_value = {
            "isPlaying": True,
            "isPaused": False,
            "isCompiling": False,
            "activeScene": "Assets/Scenes/Main.unity",
            "unityVersion": "2022.3.10f1",
        }

        result = await get_bridge_status(scan_all_ports=True)
        assert result.success is True
        assert result.connected is True
        assert result.active_port == 7890
        assert result.latency_ms == 1.2
        assert len(result.scanned_ports) == 2
        assert result.editor_state is not None
        assert result.editor_state.is_playing is True
        assert result.editor_state.active_scene == "Assets/Scenes/Main.unity"
        assert "Connected to Unity Editor on port 7890" in result.message


@pytest.mark.anyio
async def test_get_bridge_status_disconnected() -> None:
    with (
        patch("backend.tools.bridge.health.bridge.scan_available_ports", new_callable=AsyncMock) as mock_scan,
        patch("backend.tools.bridge.health.bridge.ping", new_callable=AsyncMock) as mock_ping,
    ):
        mock_scan.return_value = [
            {"port": 7890, "is_open": False, "latency_ms": None},
            {"port": 7891, "is_open": False, "latency_ms": None},
        ]
        mock_ping.return_value = (False, None)

        result = await get_bridge_status(scan_all_ports=True)
        assert result.success is False
        assert result.connected is False
        assert result.active_port is None
        assert result.error == "Unity bridge is unreachable"
        assert result.troubleshooting is not None
        assert "Ensure Unity Editor is open" in result.troubleshooting


@pytest.mark.anyio
async def test_check_ticket_status_success() -> None:
    with patch("backend.tools.bridge.queue.bridge.get_queue_status", new_callable=AsyncMock) as mock_queue:
        mock_queue.return_value = {
            "status": "completed",
            "progress": 1.0,
            "result": {"output": "Done"},
        }

        result = await check_ticket_status(ticket_id="ticket-123")
        assert result.success is True
        assert result.ticket_id == "ticket-123"
        assert result.status == "completed"
        assert result.progress == 1.0
        assert result.result == {"output": "Done"}


@pytest.mark.anyio
async def test_check_ticket_status_failed() -> None:
    with patch("backend.tools.bridge.queue.bridge.get_queue_status", new_callable=AsyncMock) as mock_queue:
        mock_queue.return_value = {
            "status": "failed",
            "progress": 0.5,
            "error": "NullReferenceException in task",
        }

        result = await check_ticket_status(ticket_id="ticket-failed")
        assert result.success is False
        assert result.status == "failed"
        assert result.error == "NullReferenceException in task"


@pytest.mark.anyio
async def test_check_ticket_status_bridge_error() -> None:
    with patch("backend.tools.bridge.queue.bridge.get_queue_status", side_effect=BridgeError("Connection dropped")):
        result = await check_ticket_status(ticket_id="ticket-err")
        assert result.success is False
        assert result.status == "error"
        assert "Bridge communication error" in (result.error or "")


@pytest.mark.anyio
async def test_wait_for_ticket_completion() -> None:
    responses = [
        {"status": "running", "progress": 0.5},
        {"status": "completed", "progress": 1.0, "result": "Baked"},
    ]

    with patch("backend.tools.bridge.queue.bridge.get_queue_status", side_effect=responses):
        result = await wait_for_ticket(ticket_id="ticket-poll", timeout=5.0, poll_interval=0.01)
        assert result.success is True
        assert result.status == "completed"
        assert result.progress == 1.0
        assert result.result == "Baked"
        assert result.duration_seconds is not None


@pytest.mark.anyio
async def test_wait_for_ticket_timeout() -> None:
    with patch(
        "backend.tools.bridge.queue.bridge.get_queue_status",
        return_value={"status": "running", "progress": 0.2},
    ):
        result = await wait_for_ticket(ticket_id="ticket-timeout", timeout=0.02, poll_interval=0.01)
        assert result.success is False
        assert result.status == "timeout"
        assert "timed out" in (result.error or "")
