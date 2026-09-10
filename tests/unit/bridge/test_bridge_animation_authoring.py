import httpx
import pytest

from backend.bridge import UnityBridge
from backend.tools.animation.common import _require_edit_mode, _unwrap_legacy_result


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_set_keyframe_native_sends_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    async def fake_request(_self: object, _method: str, path: str, **kwargs: object) -> httpx.Response:
        sent["path"] = path
        json_payload = kwargs.get("json")
        if isinstance(json_payload, dict):
            sent.update(json_payload)
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    client = UnityBridge()

    await client.set_keyframe_native(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        values=[1.0, 2.0, 3.0],
        tangent_mode="smooth",
        in_tangent=None,
        out_tangent=None,
    )

    assert sent["path"] == "/api/visora/animation/keyframes/set"
    assert sent["values"] == [1.0, 2.0, 3.0]
    assert sent["tangentMode"] == "smooth"
    assert isinstance(sent["operationId"], str)
    assert len(sent["operationId"]) > 0


@pytest.mark.anyio
async def test_set_keyframe_native_reuses_one_operation_id_across_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_operation_ids: list[str] = []
    attempts = 0

    async def fake_get_active_port(_self: object, force_refresh: bool = False) -> int:
        return 7890

    async def fake_transport_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        json_payload = kwargs.get("json")
        if isinstance(json_payload, dict):
            seen_operation_ids.append(str(json_payload["operationId"]))
        request = httpx.Request(method, url)
        if attempts == 1:
            raise httpx.ReadTimeout("simulated drop", request=request)
        return httpx.Response(200, json={"success": True}, request=request)

    monkeypatch.setattr(UnityBridge, "get_active_port", fake_get_active_port)
    client = UnityBridge()
    monkeypatch.setattr(client.client, "request", fake_transport_request)

    await client.set_keyframe_native(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        values=[1.0, 2.0, 3.0],
        tangent_mode="smooth",
        in_tangent=None,
        out_tangent=None,
    )

    assert attempts == 2
    assert len(set(seen_operation_ids)) == 1


@pytest.mark.anyio
async def test_remove_event_native_sends_null_function_name_for_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    async def fake_request(_self: object, _method: str, path: str, **kwargs: object) -> httpx.Response:
        sent["path"] = path
        json_payload = kwargs.get("json")
        if isinstance(json_payload, dict):
            sent.update(json_payload)
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    client = UnityBridge()

    await client.remove_event_native(clip_path="Assets/A.anim", time=0.5, function_name=None)

    assert sent["path"] == "/api/visora/animation/events/remove"
    assert sent["functionName"] is None


@pytest.mark.anyio
async def test_require_edit_mode_rejects_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_editor_state(_self: object) -> dict[str, object]:
        return {"isPlaying": True}

    monkeypatch.setattr(UnityBridge, "get_editor_state", fake_get_editor_state)

    error = await _require_edit_mode()

    assert error is not None
    assert "Edit Mode" in error


@pytest.mark.anyio
async def test_require_edit_mode_allows_edit_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_editor_state(_self: object) -> dict[str, object]:
        return {"isPlaying": False}

    monkeypatch.setattr(UnityBridge, "get_editor_state", fake_get_editor_state)

    assert await _require_edit_mode() is None


def test_unwrap_legacy_result_reads_the_inner_result() -> None:
    outer = {"success": True, "logs": [], "result": {"success": False, "error": "Clip not found"}}

    assert _unwrap_legacy_result(outer) == {"success": False, "error": "Clip not found"}


def test_unwrap_legacy_result_passes_through_when_there_is_no_result_key() -> None:
    already_flat = {"success": True, "clipPath": "Assets/A.anim"}

    assert _unwrap_legacy_result(already_flat) == already_flat
