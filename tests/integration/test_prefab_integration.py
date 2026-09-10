"""Contract coverage for the prefab inspection bridge call and its unsupported-bridge path."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import backend.tools.prefab as prefab_pkg
from backend.bridge import BridgeTimeoutError, UnityBridge
from backend.config import get_settings
from backend.tools.prefab.inspection import inspect_prefab_asset


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_inspect_prefab_asset_native_sends_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_request(_self: object, method: str, path: str, **kwargs: Any) -> httpx.Response:
        sent["method"] = method
        sent["path"] = path
        payload = kwargs.get("json")
        if isinstance(payload, dict):
            sent.update(payload)
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    client = UnityBridge()

    await client.inspect_prefab_asset_native(asset_path="Assets/Prefabs/Enemy.prefab", max_objects=42)

    assert sent["method"] == "POST"
    assert sent["path"] == "/api/visora/prefab/inspect"
    assert sent["assetPath"] == "Assets/Prefabs/Enemy.prefab"
    assert sent["maxObjects"] == 42


@pytest.mark.anyio
async def test_inspect_prefab_asset_native_round_trips_a_full_unity_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The native bridge shape (camelCase, Unity-side truncation) must map onto the typed result as-is."""
    unity_response = {
        "success": True,
        "assetPath": "Assets/Prefabs/Enemy.prefab",
        "prefabName": "Enemy",
        "assetGuid": "9f2a",
        "prefabKind": "regular",
        "basePrefabPath": None,
        "rootObjectName": "Enemy",
        "rootConnectionStatus": "not_an_instance",
        "hierarchy": [
            {
                "relativePath": "",
                "name": "Enemy",
                "depth": 0,
                "activeSelf": True,
                "components": [{"typeName": "Transform", "isMissingScript": False}],
                "isNestedPrefabInstanceRoot": False,
                "nestedSourceAssetPath": None,
            }
        ],
        "nestedPrefabs": [],
        "editTargetAssetPaths": ["Assets/Prefabs/Enemy.prefab"],
        "totalObjectCount": 1,
        "totalComponentCount": 1,
        "truncated": False,
        "warnings": [],
    }

    async def fake_request(_self: object, _method: str, path: str, **_kwargs: Any) -> httpx.Response:
        if path == "/api/visora/info":
            return httpx.Response(200, json={"success": True, "supportedFeatures": ["prefab_asset_inspection"]})
        if path == "/api/editor/state":
            return httpx.Response(200, json={"success": True, "isPlaying": False, "isCompiling": False})
        return httpx.Response(200, json=unity_response)

    async def fake_is_native(_self: object, force_refresh: bool = False) -> bool:
        return True

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    monkeypatch.setattr(UnityBridge, "is_native_bridge", fake_is_native)
    monkeypatch.setattr(prefab_pkg, "bridge", UnityBridge())

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is True
    assert result.prefab_kind == "regular"
    assert result.guid == "9f2a"
    assert result.base_prefab_path is None
    assert result.root_connection_status == "not_an_instance"
    assert result.hierarchy[0].relative_path == ""
    assert result.edit_target_asset_paths == ["Assets/Prefabs/Enemy.prefab"]


@pytest.mark.anyio
async def test_legacy_bridge_reports_unsupported_capability_without_executing_csharp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    An AnkleBreaker bridge gets an explicit unsupported-capability result.

    Prefab inspection is deliberately native-only: emulating Unity's isolated prefab content
    lifecycle through arbitrary `execute_code` C# would be the one path that could leak a loaded
    prefab into the user's project, so there is no legacy fallback to fall back to.
    """
    executed: list[str] = []

    class _LegacyBridge:
        async def supports_feature(self, _feature: str) -> bool:
            return False

        async def execute_code(self, code: str) -> dict[str, Any]:
            executed.append(code)
            return {"success": True, "result": {}}

        async def wait_for_editor_ready(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
            del timeout_seconds
            raise AssertionError("Editor readiness must not be probed once the capability is missing.")

        async def inspect_prefab_asset_native(self, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("A legacy bridge has no native prefab endpoint.")

    monkeypatch.setattr(prefab_pkg, "bridge", _LegacyBridge())

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert "prefab_asset_inspection" in (result.error or "")
    assert executed == []


@pytest.mark.anyio
async def test_unreadable_capability_probe_is_treated_as_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenBridge:
        async def supports_feature(self, _feature: str) -> bool:
            raise RuntimeError("bridge unreachable")

    monkeypatch.setattr(prefab_pkg, "bridge", _BrokenBridge())

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert "prefab_asset_inspection" in (result.error or "")


def test_prefab_node_limit_is_configurable_and_bounded() -> None:
    assert get_settings().prefab_max_hierarchy_nodes > 0


@pytest.mark.anyio
async def test_inspect_prefab_asset_native_transport_timeout_surfaces_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TimeoutBridge:
        async def supports_feature(self, _feature: str) -> bool:
            return True

        async def wait_for_editor_ready(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
            del timeout_seconds
            return {"isPlaying": False, "isCompiling": False}

        async def inspect_prefab_asset_native(self, **_kwargs: Any) -> dict[str, Any]:
            raise BridgeTimeoutError(
                message="Bridge request to '/api/visora/prefab/inspect' timed out after 10.0s.",
                timeout_seconds=10.0,
            )

    monkeypatch.setattr(prefab_pkg, "bridge", _TimeoutBridge())

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert result.retryable is False
    assert "timed out after 10.0s" in (result.error or "")


@pytest.mark.anyio
async def test_inspect_prefab_asset_native_model_prefab_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_response = {
        "success": True,
        "assetPath": "Assets/Models/Hero.fbx",
        "prefabName": "Hero",
        "assetGuid": "a1b2c3d4",
        "prefabKind": "model",
        "basePrefabPath": None,
        "rootObjectName": "Hero",
        "rootConnectionStatus": "not_an_instance",
        "hierarchy": [
            {
                "relativePath": "",
                "name": "Hero",
                "depth": 0,
                "activeSelf": True,
                "components": [{"typeName": "Transform", "isMissingScript": False}],
                "isNestedPrefabInstanceRoot": False,
                "nestedSourceAssetPath": None,
            },
            {
                "relativePath": "Mesh",
                "name": "Mesh",
                "depth": 1,
                "activeSelf": True,
                "components": [{"typeName": "MeshFilter", "isMissingScript": False}],
                "isNestedPrefabInstanceRoot": False,
                "nestedSourceAssetPath": None,
            },
        ],
        "nestedPrefabs": [],
        "editTargetAssetPaths": [],
        "totalObjectCount": 2,
        "totalComponentCount": 2,
        "truncated": False,
        "warnings": ["Model Prefabs are read-only."],
    }

    async def fake_request(_self: object, _method: str, path: str, **_kwargs: Any) -> httpx.Response:
        if path == "/api/visora/info":
            return httpx.Response(200, json={"success": True, "supportedFeatures": ["prefab_asset_inspection"]})
        if path == "/api/editor/state":
            return httpx.Response(200, json={"success": True, "isPlaying": False, "isCompiling": False})
        return httpx.Response(200, json=model_response)

    async def fake_is_native(_self: object, force_refresh: bool = False) -> bool:
        return True

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    monkeypatch.setattr(UnityBridge, "is_native_bridge", fake_is_native)
    monkeypatch.setattr(prefab_pkg, "bridge", UnityBridge())

    result = await inspect_prefab_asset("Assets/Models/Hero.fbx")

    assert result.success is True
    assert result.prefab_kind == "model"
    assert result.asset_path == "Assets/Models/Hero.fbx"
    assert result.edit_target_asset_paths == []
    assert len(result.hierarchy) == 2
    assert result.hierarchy[1].relative_path == "Mesh"
    assert "Model Prefabs are read-only." in result.warnings
