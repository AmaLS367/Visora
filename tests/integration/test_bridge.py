from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.bridge import (
    BridgeBusyError,
    BridgeConnectionError,
    BridgeError,
    BridgeHTTPError,
    BridgeProtocolError,
    BridgeTimeoutError,
    UnityBridge,
)
from backend.config import Settings
from backend.tools.bridge.health import get_bridge_status
from backend.tools.bridge.queue import check_ticket_status
from backend.tools.errors import bridge_error


@pytest.fixture(autouse=True)
def _no_local_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings() loads ".env" relative to the current working directory (see the identical
    fixture in test_config.py). mock_settings and test_candidate_ports_with_custom_list_and_
    duplicates below construct Settings() without overriding unity_bridge_mode, so they silently
    depended on the repo's own .env being absent or having UNITY_BRIDGE_MODE=legacy - real live
    testing that switched .env to native mode broke five tests here that were never actually
    pinning the mode they test against.
    """
    monkeypatch.chdir(tmp_path)


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
        unity_bridge_state_probe_timeout_seconds=0.2,
        unity_bridge_ready_wait_seconds=1.0,
    )


@pytest.mark.anyio
async def test_candidate_ports_ordering(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    assert bridge.candidate_ports == [7890, 7891, 7892, 7893]


@pytest.mark.anyio
async def test_candidate_ports_with_custom_list_and_duplicates() -> None:
    settings = Settings(
        unity_bridge_port=8000,
        unity_bridge_fallback_port=8001,
        unity_bridge_ports_to_scan=[8000, 8001, 8002, 8003, 8000],
    )
    bridge = UnityBridge(settings=settings)
    assert bridge.candidate_ports == [8000, 8001, 8002, 8003]


@pytest.mark.anyio
async def test_bridge_exceptions_attributes() -> None:
    # BridgeConnectionError
    conn_err = BridgeConnectionError("Unreachable", ports=[7890, 7891])
    assert conn_err.ports == [7890, 7891]
    assert "Unreachable" in str(conn_err)

    # BridgeHTTPError
    http_err = BridgeHTTPError("Bad Request", status_code=400, response_body='{"err": "bad"}')
    assert http_err.status_code == 400
    assert http_err.response_body == '{"err": "bad"}'
    assert "Bad Request" in str(http_err)

    # BridgeTimeoutError
    time_err = BridgeTimeoutError("Timed out", timeout_seconds=12.5)
    assert time_err.timeout_seconds == 12.5
    assert "Timed out" in str(time_err)


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
async def test_legacy_mode_ignores_native_bridge(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_ports_to_scan": [7890, 7891]}))

    def side_effect(url: str, **_kwargs: Any) -> httpx.Response:
        flavor = "visora-native" if ":7890" in url else "anklebreaker"
        return httpx.Response(200, json={"success": True, "flavor": flavor}, request=httpx.Request("GET", url))

    with patch.object(bridge.client, "get", side_effect=side_effect):
        assert await bridge.get_active_port() == 7891
        assert await bridge.get_bridge_flavor() == "anklebreaker"


@pytest.mark.anyio
async def test_auto_mode_prefers_legacy_bridge(mock_settings: Settings) -> None:
    bridge = UnityBridge(
        settings=mock_settings.model_copy(
            update={"unity_bridge_mode": "auto", "unity_bridge_ports_to_scan": [7890, 7891]}
        )
    )

    def side_effect(url: str, **_kwargs: Any) -> httpx.Response:
        flavor = "visora-native" if ":7890" in url else "anklebreaker"
        return httpx.Response(200, json={"success": True, "flavor": flavor}, request=httpx.Request("GET", url))

    with patch.object(bridge.client, "get", side_effect=side_effect):
        assert await bridge.get_active_port() == 7891
        assert await bridge.get_bridge_flavor() == "anklebreaker"


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
async def test_ping_without_port_triggers_active_port_discovery(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    mock_req = httpx.Request("GET", "http://127.0.0.1:7890/api/ping")
    with patch.object(bridge.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json={"status": "ok"}, request=mock_req)
        ok, latency = await bridge.ping()
        assert ok is True
        assert latency is not None
        assert bridge._active_port == 7890


@pytest.mark.anyio
async def test_ping_without_port_when_bridge_unreachable(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    with patch.object(bridge.client, "get", side_effect=httpx.ConnectError("Unreachable")):
        ok, latency = await bridge.ping()
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
        # ensure_ready=False isolates the retry/timeout path from the readiness guard, which would
        # otherwise intercept the same ReadTimeout during its editor-state probe.
        with pytest.raises(BridgeTimeoutError) as excinfo:
            await bridge._request("POST", "/api/editor/execute-code", ensure_ready=False)
        assert excinfo.value.timeout_seconds == 5.0


@pytest.mark.anyio
async def test_unity_bridge_methods(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    mock_req = httpx.Request("POST", "http://127.0.0.1:7890")

    with patch.object(bridge, "_request", new_callable=AsyncMock) as mock_request:
        # execute_code
        mock_request.return_value = httpx.Response(200, json={"success": True, "result": 123}, request=mock_req)
        res = await bridge.execute_code("Debug.Log(1);")
        assert res == {"success": True, "result": 123}
        mock_request.assert_called_with(
            "POST",
            "/api/editor/execute-code",
            json={"code": "Debug.Log(1);", "timeoutSeconds": 60.0},
            timeout=60.0,
            retry_on_timeout=False,
        )

        # get_editor_state
        mock_request.return_value = httpx.Response(200, json={"isPlaying": False}, request=mock_req)
        res = await bridge.get_editor_state()
        assert res == {"isPlaying": False}
        mock_request.assert_called_with("POST", "/api/editor/state", recover=False)

        # set_play_mode
        mock_request.return_value = httpx.Response(200, json={"isPlaying": True}, request=mock_req)
        res = await bridge.set_play_mode(True)
        assert res == {"isPlaying": True}
        mock_request.assert_called_with(
            "POST", "/api/editor/play-mode", json={"action": "play"}, recover=False, retry_on_timeout=False
        )

        # save_scene
        mock_request.return_value = httpx.Response(200, json={"saved": True}, request=mock_req)
        res = await bridge.save_scene()
        assert res == {"saved": True}
        mock_request.assert_called_with("POST", "/api/scene/save", retry_on_timeout=False)

        # get_compilation_errors
        mock_request.return_value = httpx.Response(200, json={"errors": []}, request=mock_req)
        res = await bridge.get_compilation_errors()
        assert res == {"errors": []}
        mock_request.assert_called_with("GET", "/api/compilation/errors", recover=False)

        # get_queue_status
        mock_request.return_value = httpx.Response(200, json={"status": "completed"}, request=mock_req)
        res = await bridge.get_queue_status("t-1")
        assert res == {"status": "completed"}
        mock_request.assert_called_with("GET", "/api/queue/status", params={"ticketId": "t-1"}, recover=False)

        # cancel_queue_ticket
        mock_request.return_value = httpx.Response(200, json={"cancelled": True}, request=mock_req)
        res = await bridge.cancel_queue_ticket("t-1")
        assert res == {"cancelled": True}
        mock_request.assert_called_with("POST", "/api/queue/cancel", json={"ticketId": "t-1"}, recover=False)


@pytest.mark.anyio
async def test_healthy_request_makes_no_extra_probe(mock_settings: Settings) -> None:
    """A healthy call costs exactly one request - the reactive guard never probes preemptively."""
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890
    urls: list[str] = []

    def side_effect(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        urls.append(url)
        return httpx.Response(200, json={"success": True, "result": 1}, request=httpx.Request(method, url))

    with patch.object(bridge.client, "request", side_effect=side_effect):
        result = await bridge.execute_code("return 1;")

    assert result == {"success": True, "result": 1}
    assert urls == ["http://127.0.0.1:7890/api/editor/execute-code"]
    assert not any("/api/editor/state" in u for u in urls)


@pytest.mark.anyio
async def test_connection_drop_recovers_and_retries_once(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890
    bridge._last_good_port = 7890
    work_calls = 0

    def side_effect(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        nonlocal work_calls
        req = httpx.Request(method, url)
        if "/api/editor/state" in url:
            return httpx.Response(200, json={"isCompiling": False, "isUpdating": False}, request=req)
        work_calls += 1
        if work_calls == 1:
            raise httpx.ConnectError("socket dropped mid-reload", request=req)
        return httpx.Response(200, json={"success": True}, request=req)

    with patch.object(bridge.client, "request", side_effect=side_effect):
        result = await bridge.execute_code("return 1;")

    assert result == {"success": True}
    assert work_calls == 2  # 1 initial dropped attempt + 1 post-recovery retry


@pytest.mark.anyio
async def test_recovery_gives_up_with_reason_compiling(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_ready_wait_seconds": 0.05}))
    bridge._active_port = 7890
    bridge._last_good_port = 7890

    def side_effect(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        req = httpx.Request(method, url)
        if "/api/editor/state" in url:
            return httpx.Response(200, json={"isCompiling": True, "isUpdating": False}, request=req)
        raise httpx.ConnectError("socket dropped", request=req)

    with patch.object(bridge.client, "request", side_effect=side_effect):
        with pytest.raises(BridgeBusyError) as excinfo:
            await bridge.execute_code("return 1;")

    assert excinfo.value.reason == "compiling"
    assert excinfo.value.retry_after_seconds == 3.0


@pytest.mark.anyio
async def test_recovery_reason_is_reloading_when_bridge_stays_down(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_ready_wait_seconds": 0.05}))
    bridge._active_port = 7890
    bridge._last_good_port = 7890

    with (
        patch.object(bridge.client, "request", side_effect=httpx.ConnectError("still down")),
        patch.object(bridge.client, "get", side_effect=httpx.ConnectError("still down")),
    ):
        with pytest.raises(BridgeBusyError) as excinfo:
            await bridge.execute_code("return 1;")

    # A known port that went quiet reads as a reload, not an outright unreachable bridge.
    assert excinfo.value.reason == "reloading"


@pytest.mark.anyio
async def test_unusable_reload_body_triggers_recovery(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890
    bridge._last_good_port = 7890
    work_calls = 0

    def side_effect(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        nonlocal work_calls
        req = httpx.Request(method, url)
        if "/api/editor/state" in url:
            return httpx.Response(200, json={"isCompiling": False, "isUpdating": False}, request=req)
        work_calls += 1
        if work_calls == 1:
            return httpx.Response(200, text="", request=req)  # mid-reload empty body
        return httpx.Response(200, json={"success": True}, request=req)

    with patch.object(bridge.client, "request", side_effect=side_effect):
        result = await bridge.execute_code("return 1;")

    assert result == {"success": True}
    assert work_calls == 2


@pytest.mark.anyio
async def test_execute_code_read_timeout_is_not_retried_or_recovered(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890
    urls: list[str] = []

    def side_effect(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        urls.append(url)
        raise httpx.ReadTimeout("no response", request=httpx.Request(method, url))

    with patch.object(bridge.client, "request", side_effect=side_effect):
        with pytest.raises(BridgeTimeoutError):
            await bridge.execute_code("DestroyImmediate(go);")

    # Exactly one send, and no editor-state probe: the request may have landed, so we never resend.
    assert urls == ["http://127.0.0.1:7890/api/editor/execute-code"]


@pytest.mark.anyio
async def test_last_good_port_is_preferred_on_reconnect(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    assert bridge.candidate_ports == [7890, 7891, 7892, 7893]

    bridge._last_good_port = 7892
    assert bridge.candidate_ports[0] == 7892
    assert sorted(bridge.candidate_ports) == [7890, 7891, 7892, 7893]


@pytest.mark.anyio
async def test_unreachable_bridge_never_triggers_recovery(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = None
    bridge._last_good_port = None

    with (
        patch.object(bridge.client, "request", side_effect=httpx.ConnectError("refused")),
        patch.object(bridge.client, "get", side_effect=httpx.ConnectError("refused")),
    ):
        with pytest.raises(BridgeConnectionError):
            await bridge.execute_code("return 1;")


def test_bridge_error_never_marks_unreachable_as_retryable() -> None:
    unreachable_busy = BridgeBusyError(reason="unreachable")
    fields = bridge_error(unreachable_busy)
    assert fields["success"] is False
    assert fields.get("retryable") is not True

    compiling_busy = BridgeBusyError(reason="compiling", retry_after_seconds=3.0)
    comp_fields = bridge_error(compiling_busy)
    assert comp_fields["success"] is False
    assert comp_fields["retryable"] is True
    assert comp_fields["unity_state"] == "compiling"
    assert comp_fields["retry_after_seconds"] == 3.0


@pytest.mark.anyio
async def test_execute_capability_forwards_retry_on_timeout(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_mode": "native"}))
    bridge._active_port = 7890
    bridge._bridge_flavor = "visora-native"

    with patch.object(bridge, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = httpx.Response(
            200, json={"success": True}, request=httpx.Request("POST", "http://127.0.0.1:7890/api/test")
        )
        await bridge.execute_capability(
            "return 1;", native_path="/api/test", native_payload={"k": "v"}, retry_on_timeout=False
        )
        mock_req.assert_called_with("POST", "/api/test", json={"k": "v"}, retry_on_timeout=False)


@pytest.mark.anyio
async def test_timeout_message_reflects_actual_timeout(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890

    def side_effect(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=httpx.Request(method, url))

    with patch.object(bridge.client, "request", side_effect=side_effect):
        with pytest.raises(BridgeTimeoutError) as excinfo:
            await bridge.execute_code("return 1;")

    assert "60.0s" in str(excinfo.value)
    assert excinfo.value.timeout_seconds == 60.0


@pytest.mark.anyio
async def test_wait_for_play_mode_success_and_timeout(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    # 1. Immediate match
    with patch.object(bridge, "get_editor_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = {"isPlaying": True, "isCompiling": False, "isUpdating": False}
        state = await bridge.wait_for_play_mode(target_playing=True, timeout_seconds=1.0)
        assert state["isPlaying"] is True

    # 2. Retries through temporary connection drops, then succeeds
    call_count = 0

    async def transient_error_state() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise BridgeConnectionError("Port closed", ports=[7890])
        return {"isPlaying": False, "isCompiling": False, "isUpdating": False}

    with patch.object(bridge, "get_editor_state", side_effect=transient_error_state):
        state = await bridge.wait_for_play_mode(target_playing=False, timeout_seconds=2.0, poll_interval_seconds=0.01)
        assert state["isPlaying"] is False
        assert call_count >= 2

    # 3. Timeout raises BridgeTimeoutError
    with patch.object(bridge, "get_editor_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = {"isPlaying": False, "isCompiling": True, "isUpdating": False}
        with pytest.raises(BridgeTimeoutError) as excinfo:
            await bridge.wait_for_play_mode(target_playing=True, timeout_seconds=0.05, poll_interval_seconds=0.01)
        assert "Timed out" in excinfo.value.message


@pytest.mark.anyio
async def test_wait_for_editor_ready_success_and_timeout(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)

    with patch.object(bridge, "get_editor_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = {"isPlaying": False, "isCompiling": False, "isUpdating": False}
        state = await bridge.wait_for_editor_ready(timeout_seconds=1.0)
        assert state["isCompiling"] is False

    with patch.object(bridge, "get_editor_state", new_callable=AsyncMock) as mock_state:
        mock_state.return_value = {"isPlaying": False, "isCompiling": True, "isUpdating": False}
        with pytest.raises(BridgeTimeoutError):
            await bridge.wait_for_editor_ready(timeout_seconds=0.05, poll_interval_seconds=0.01)


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
async def test_check_ticket_status_cancelled() -> None:
    with patch("backend.tools.bridge.queue.bridge.get_queue_status", new_callable=AsyncMock) as mock_queue:
        mock_queue.return_value = {
            "status": "cancelled",
            "progress": 0.3,
        }

        result = await check_ticket_status(ticket_id="ticket-cancel")
        assert result.success is False
        assert result.status == "cancelled"
        assert result.error == "Task was cancelled"


@pytest.mark.anyio
async def test_check_ticket_status_running() -> None:
    with patch("backend.tools.bridge.queue.bridge.get_queue_status", new_callable=AsyncMock) as mock_queue:
        mock_queue.return_value = {
            "status": "running",
            "progress": 0.4,
            "result": {"temp": True},
        }

        result = await check_ticket_status(ticket_id="ticket-run")
        assert result.success is True
        assert result.status == "running"
        assert result.progress == 0.4
        assert result.result == {"temp": True}


@pytest.mark.anyio
async def test_check_ticket_status_bridge_error() -> None:
    with patch("backend.tools.bridge.queue.bridge.get_queue_status", side_effect=BridgeError("Connection dropped")):
        result = await check_ticket_status(ticket_id="ticket-err")
        assert result.success is False
        assert result.status == "error"
        assert "Bridge communication error" in (result.error or "")


@pytest.mark.anyio
async def test_check_ticket_status_unexpected_exception() -> None:
    with patch("backend.tools.bridge.queue.bridge.get_queue_status", side_effect=ValueError("Corrupt JSON")):
        result = await check_ticket_status(ticket_id="ticket-exc")
        assert result.success is False
        assert result.status == "error"
        assert "Corrupt JSON" in (result.error or "")


@pytest.mark.anyio
async def test_check_ticket_status_wait_completion() -> None:
    responses = [
        {"status": "running", "progress": 0.5},
        {"status": "completed", "progress": 1.0, "result": "Baked"},
    ]

    with patch("backend.tools.bridge.queue.bridge.get_queue_status", side_effect=responses):
        result = await check_ticket_status(
            ticket_id="ticket-poll", wait=True, timeout_seconds=5.0, poll_interval_seconds=0.01
        )
        assert result.success is True
        assert result.status == "completed"
        assert result.progress == 1.0
        assert result.result == "Baked"
        assert result.duration_seconds is not None


@pytest.mark.anyio
async def test_check_ticket_status_wait_cancelled() -> None:
    with patch(
        "backend.tools.bridge.queue.bridge.get_queue_status",
        return_value={"status": "cancelled", "progress": 0.2},
    ):
        result = await check_ticket_status(
            ticket_id="ticket-cancelled", wait=True, timeout_seconds=5.0, poll_interval_seconds=0.01
        )
        assert result.success is False
        assert result.status == "cancelled"
        assert "cancelled in Unity Editor" in (result.error or "")


@pytest.mark.anyio
async def test_check_ticket_status_wait_failed_with_error_message() -> None:
    with patch(
        "backend.tools.bridge.queue.bridge.get_queue_status",
        return_value={"status": "failed", "progress": 0.1, "errorMessage": "Out of memory"},
    ):
        result = await check_ticket_status(
            ticket_id="ticket-fail-msg", wait=True, timeout_seconds=5.0, poll_interval_seconds=0.01
        )
        assert result.success is False
        assert result.status == "failed"
        assert result.error == "Out of memory"


@pytest.mark.anyio
async def test_check_ticket_status_wait_transient_error_recovery() -> None:
    responses = [
        httpx.ConnectError("Transient connection drop"),
        {"status": "completed", "progress": 1.0, "result": {"baked": True}},
    ]

    with patch("backend.tools.bridge.queue.bridge.get_queue_status", side_effect=responses):
        result = await check_ticket_status(
            ticket_id="ticket-recover", wait=True, timeout_seconds=5.0, poll_interval_seconds=0.01
        )
        assert result.success is True
        assert result.status == "completed"
        assert result.result == {"baked": True}


@pytest.mark.anyio
async def test_check_ticket_status_wait_timeout() -> None:
    with patch(
        "backend.tools.bridge.queue.bridge.get_queue_status",
        return_value={"status": "running", "progress": 0.2},
    ):
        result = await check_ticket_status(
            ticket_id="ticket-timeout", wait=True, timeout_seconds=0.02, poll_interval_seconds=0.01
        )
        assert result.success is False
        assert result.status == "timeout"
        assert "timed out" in (result.error or "")


@pytest.mark.anyio
async def test_native_bridge_flavor_and_info(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_mode": "native"}))

    mock_ping = httpx.Response(
        200,
        json={"success": True, "flavor": "visora-native", "version": "1.1.0"},
        request=httpx.Request("GET", "http://127.0.0.1:7890/api/ping"),
    )
    mock_info = httpx.Response(
        200,
        json={
            "success": True,
            "flavor": "visora-native",
            "version": "1.1.0",
            "apiVersion": 2,
            "supportedFeatures": ["camera_render"],
        },
        request=httpx.Request("GET", "http://127.0.0.1:7890/api/visora/info"),
    )

    def side_effect(method: str, url: str, **kwargs: Any) -> httpx.Response:
        if "/api/ping" in url:
            return mock_ping
        if "/api/visora/info" in url:
            return mock_info
        return httpx.Response(404, request=httpx.Request(method, url))

    with patch.object(bridge.client, "request", side_effect=side_effect):
        with patch.object(bridge.client, "get", return_value=mock_ping):
            flavor = await bridge.get_bridge_flavor()
            assert flavor == "visora-native"
            assert await bridge.is_native_bridge() is True

            info = await bridge.get_bridge_info()
            assert info["flavor"] == "visora-native"
            assert "camera_render" in info["supportedFeatures"]


@pytest.mark.anyio
async def test_native_endpoints_execution(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890

    # Test camera render native
    mock_render_resp = httpx.Response(
        200,
        json={"success": True, "imageBase64": "abc"},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/camera/render"),
    )
    with patch.object(bridge.client, "request", return_value=mock_render_resp):
        res = await bridge.render_camera_native(camera_name="Main Camera")
        assert res["success"] is True
        assert res["imageBase64"] == "abc"


@pytest.mark.anyio
async def test_render_camera_uses_native_endpoint_in_native_mode(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_mode": "native"}))
    bridge._active_port = 7890
    bridge._bridge_flavor = "visora-native"
    request = httpx.Request("POST", "http://127.0.0.1:7890/api/visora/camera/render")

    with patch.object(
        bridge.client, "request", return_value=httpx.Response(200, json={"success": True}, request=request)
    ):
        result = await bridge.render_camera("return null;", "Main Camera", 320, 180)

    assert result == {"success": True}


@pytest.mark.anyio
async def test_native_capability_falls_back_to_native_executor_when_no_typed_endpoint(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_mode": "native"}))
    bridge._active_port = 7890
    bridge._bridge_flavor = "visora-native"

    with patch.object(bridge, "execute_code", new_callable=AsyncMock, return_value={"success": True}) as execute_code:
        result = await bridge.execute_capability("return null;")

    assert result == {"success": True}
    execute_code.assert_awaited_once_with("return null;")

    # Test sequence capture native
    mock_seq_resp = httpx.Response(
        200,
        json={"success": True, "frames": [{"frameIndex": 0, "imageBase64": "f0"}]},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/camera/sequence"),
    )
    with patch.object(bridge.client, "request", return_value=mock_seq_resp):
        res = await bridge.capture_sequence_native(camera_name="Main Camera", frame_count=1)
        assert res["success"] is True
        assert len(res["frames"]) == 1

    # Test mesh diagnose native
    mock_mesh_resp = httpx.Response(
        200,
        json={"success": True, "vertexCount": 100},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/mesh/diagnose"),
    )
    with patch.object(bridge.client, "request", return_value=mock_mesh_resp):
        res = await bridge.diagnose_mesh_native("Character")
        assert res["vertexCount"] == 100

    # Test skeleton diagnose native
    mock_skel_resp = httpx.Response(
        200,
        json={"success": True, "totalBones": 20},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/skeleton/diagnose"),
    )
    with patch.object(bridge.client, "request", return_value=mock_skel_resp):
        res = await bridge.diagnose_skeleton_native("Root", "Hand")
        assert res["totalBones"] == 20

    # Test animation inspect native
    mock_anim_resp = httpx.Response(
        200,
        json={"success": True, "clipName": "Walk", "length": 1.5},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/animation/inspect"),
    )
    with patch.object(bridge.client, "request", return_value=mock_anim_resp):
        res = await bridge.inspect_clip_native("Walk")
        assert res["clipName"] == "Walk"

    # Test animation sample native
    mock_sample_resp = httpx.Response(
        200,
        json={"success": True, "clipName": "Walk", "sampleTime": 0.5},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/animation/sample"),
    )
    with patch.object(bridge.client, "request", return_value=mock_sample_resp):
        res = await bridge.sample_clip_native("Walk", "Target", 0.5)
        assert res["sampleTime"] == 0.5

    # Test transactions native
    mock_tx_begin = httpx.Response(
        200,
        json={"success": True, "transactionId": "tx_123"},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/transaction/begin"),
    )
    with patch.object(bridge.client, "request", return_value=mock_tx_begin):
        res = await bridge.begin_transaction_native("Test Op")
        assert res["transactionId"] == "tx_123"

    mock_tx_commit = httpx.Response(
        200,
        json={"success": True, "transactionId": "tx_123"},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/transaction/commit"),
    )
    with patch.object(bridge.client, "request", return_value=mock_tx_commit):
        res = await bridge.commit_transaction_native("tx_123")
        assert res["success"] is True

    mock_tx_rollback = httpx.Response(
        200,
        json={"success": True, "transactionId": "tx_123"},
        request=httpx.Request("POST", "http://127.0.0.1:7890/api/visora/transaction/rollback"),
    )
    with patch.object(bridge.client, "request", return_value=mock_tx_rollback):
        res = await bridge.rollback_transaction_native("tx_123")
        assert res["success"] is True


@pytest.mark.parametrize(
    ("body", "expected_fragment"),
    [
        ("", "empty body"),
        ("   \n ", "empty body"),
        ("<html>Unity is reloading</html>", "non-JSON body"),
        ("null", "NoneType instead of a JSON object"),
        ("[1, 2, 3]", "list instead of a JSON object"),
    ],
)
@pytest.mark.anyio
async def test_successful_response_with_unusable_body_raises_protocol_error(
    mock_settings: Settings,
    body: str,
    expected_fragment: str,
) -> None:
    """
    Unity answers 200 with an empty or non-JSON body while a domain reload is in flight. Before this
    was typed, callers got a bare JSONDecodeError that no retry path recognised.
    """
    bridge = UnityBridge(settings=mock_settings)
    request = httpx.Request("POST", "http://127.0.0.1:7890/api/editor/execute-code")
    response = httpx.Response(200, text=body, request=request)

    with patch.object(bridge, "_request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = response
        with pytest.raises(BridgeProtocolError) as excinfo:
            await bridge.execute_code("return 1;")

    assert expected_fragment in excinfo.value.message
    assert excinfo.value.status_code == 200
    assert "/api/editor/execute-code" in excinfo.value.message


@pytest.mark.anyio
async def test_wait_for_play_mode_retries_through_unusable_body(mock_settings: Settings) -> None:
    """An unusable body means Unity is still reloading, so polling must keep waiting, not fail."""
    bridge = UnityBridge(settings=mock_settings)
    call_count = 0

    async def reloading_then_ready() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise BridgeProtocolError(
                message="Bridge returned an empty body for '/api/editor/state' with status 200.",
                status_code=200,
            )
        return {"isPlaying": True, "isCompiling": False, "isUpdating": False}

    with patch.object(bridge, "get_editor_state", side_effect=reloading_then_ready):
        state = await bridge.wait_for_play_mode(target_playing=True, timeout_seconds=2.0, poll_interval_seconds=0.01)

    assert state["isPlaying"] is True
    assert call_count >= 2


@pytest.mark.anyio
async def test_wait_for_editor_ready_retries_through_unusable_body(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    call_count = 0

    async def reloading_then_ready() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise BridgeProtocolError(message="Bridge returned a non-JSON body for '/api/editor/state': '<html>'")
        return {"isPlaying": False, "isCompiling": False, "isUpdating": False}

    with patch.object(bridge, "get_editor_state", side_effect=reloading_then_ready):
        state = await bridge.wait_for_editor_ready(timeout_seconds=2.0, poll_interval_seconds=0.01)

    assert state["isCompiling"] is False
    assert call_count >= 2


@pytest.mark.anyio
async def test_port_discovery_survives_empty_ping_body(mock_settings: Settings) -> None:
    """
    A bridge mid-reload answers /api/ping with 200 and no body. Discovery must still accept the port
    rather than treating the whole bridge as unreachable - but it must not guess the flavor, because
    caching a native bridge as legacy silently disables every native capability for good.
    """
    bridge = UnityBridge(settings=mock_settings)
    request = httpx.Request("GET", "http://127.0.0.1:7890/api/ping")
    response = httpx.Response(200, text="", request=request)

    with patch.object(bridge.client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = response
        port = await bridge.get_active_port()

    assert port == 7890
    assert bridge._bridge_flavor is None


@pytest.mark.anyio
async def test_native_flavor_is_resolved_after_the_reload_finishes(mock_settings: Settings) -> None:
    """
    The flavor left unresolved during a reload must be probed again once Unity answers properly,
    instead of staying at the legacy default and pinning the client to the slow capture path.
    """
    # Native capabilities only matter outside legacy mode, which is the Settings default.
    bridge = UnityBridge(settings=mock_settings.model_copy(update={"unity_bridge_mode": "auto"}))
    probes = 0

    async def ping(url: str, **_kwargs: Any) -> httpx.Response:
        nonlocal probes
        request = httpx.Request("GET", url)
        if not url.startswith("http://127.0.0.1:7890/"):
            raise httpx.ConnectError("no bridge on this port", request=request)
        probes += 1
        if probes == 1:
            # Still reloading: 200 with nothing usable in the body.
            return httpx.Response(200, text="", request=request)
        return httpx.Response(200, json={"flavor": "visora-native"}, request=request)

    with patch.object(bridge.client, "get", side_effect=ping):
        assert await bridge.get_active_port() == 7890
        assert bridge._bridge_flavor is None

        # Unity has finished reloading by the time anything asks about capabilities.
        assert await bridge.is_native_bridge() is True

    assert bridge._bridge_flavor == "visora-native"


@pytest.mark.anyio
async def test_capabilities_are_not_cached_while_the_flavor_is_unresolved(mock_settings: Settings) -> None:
    """An unknown flavor is not a confirmed legacy bridge, so 'no capabilities' must not be cached."""
    bridge = UnityBridge(settings=mock_settings)
    bridge._active_port = 7890
    bridge._bridge_flavor = None

    with patch.object(bridge, "is_native_bridge", new_callable=AsyncMock) as mock_native:
        mock_native.return_value = False
        assert await bridge.supports_feature("camera_sequence_realtime") is False

    assert bridge._supported_features is None


@pytest.mark.anyio
async def test_capabilities_are_not_cached_after_a_transient_failure(mock_settings: Settings) -> None:
    """
    A single failed capability probe must not pin the client to the slow capture path forever: the
    next call has to ask again rather than reuse a cached "no capabilities".
    """
    bridge = UnityBridge(settings=mock_settings)
    request = httpx.Request("GET", "http://127.0.0.1:7890/api/visora/info")
    attempts = 0

    async def flaky_info(_method: str, _path: str, **_kwargs: Any) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise BridgeConnectionError("bridge briefly unreachable", ports=[7890])
        return httpx.Response(
            200,
            json={"success": True, "supportedFeatures": ["camera_sequence_realtime"]},
            request=request,
        )

    with (
        patch.object(bridge, "is_native_bridge", new_callable=AsyncMock) as mock_native,
        patch.object(bridge, "_request", side_effect=flaky_info),
    ):
        mock_native.return_value = True

        assert await bridge.supports_feature("camera_sequence_realtime") is False
        assert await bridge.supports_feature("camera_sequence_realtime") is True

    assert attempts == 2


@pytest.mark.anyio
async def test_capabilities_are_cached_once_read(mock_settings: Settings) -> None:
    bridge = UnityBridge(settings=mock_settings)
    request = httpx.Request("GET", "http://127.0.0.1:7890/api/visora/info")
    response = httpx.Response(200, json={"supportedFeatures": ["animation_preview_sequence"]}, request=request)

    with (
        patch.object(bridge, "is_native_bridge", new_callable=AsyncMock) as mock_native,
        patch.object(bridge, "_request", new_callable=AsyncMock) as mock_request,
    ):
        mock_native.return_value = True
        mock_request.return_value = response

        assert await bridge.supports_feature("animation_preview_sequence") is True
        assert await bridge.supports_feature("camera_sequence_realtime") is False

    assert mock_request.await_count == 1
