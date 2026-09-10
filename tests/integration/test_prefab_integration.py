"""Contract coverage for the prefab inspection bridge calls and their unsupported-bridge paths."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import backend.tools.prefab as prefab_pkg
from backend.bridge import BridgeHTTPError, BridgeTimeoutError, UnityBridge
from backend.config import get_settings
from backend.tools.prefab.inspection import inspect_prefab_asset
from backend.tools.prefab.overrides import inspect_prefab_overrides


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


# --------------------------------------------------------------------------------------
# inspect_prefab_overrides
# --------------------------------------------------------------------------------------


def _override_response() -> dict[str, Any]:
    return {
        "success": True,
        "instancePath": "Level/Crate/Lid",
        "scenePath": "Assets/Scenes/Main.unity",
        "instanceRootPath": "Level/Crate",
        "outermostInstanceRootPath": "Level/Crate",
        "scope": "nearest",
        "sourceAssetPath": "Assets/Prefabs/Crate.prefab",
        "sourceGuid": "abc123",
        "prefabKind": "regular",
        "connectionStatus": "connected",
        "includeDefaultOverrides": False,
        "totalOverrideCount": 1,
        "overrideCounts": {
            "modifiedProperty": 0,
            "addedComponent": 1,
            "removedComponent": 0,
            "addedGameObject": 0,
            "removedGameObject": 0,
        },
        "excludedDefaultOverrideCount": 2,
        "truncated": False,
        "overrides": [
            {
                "overrideId": "ovr_1a2b3c4d5e6f7a8b",
                "category": "added_component",
                "objectPath": "Lid",
                "sourceObjectPath": "Lid",
                "componentType": "SphereCollider",
                "componentOrdinal": None,
                "propertyPath": None,
                "sourceValue": None,
                "instanceValue": None,
                "isDefaultOverride": False,
                "targetAssetPaths": ["Assets/Prefabs/Crate.prefab"],
                "recommendedTargetAssetPath": "Assets/Prefabs/Crate.prefab",
                "applicable": True,
                "notApplicableReason": None,
                "idCollision": False,
                "description": "Added component SphereCollider on 'Lid'.",
            }
        ],
        "pathCandidates": [],
        "warnings": [],
    }


@pytest.mark.anyio
async def test_inspect_prefab_overrides_native_sends_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_request(_self: object, method: str, path: str, **kwargs: Any) -> httpx.Response:
        sent["method"] = method
        sent["path"] = path
        sent["kwargs"] = {key: value for key, value in kwargs.items() if key != "json"}
        payload = kwargs.get("json")
        if isinstance(payload, dict):
            sent.update(payload)
        return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    client = UnityBridge()

    await client.inspect_prefab_overrides_native(
        instance_path="Level/Crate/Lid",
        scene_path=None,
        include_default_overrides=True,
        scope="outermost",
        max_overrides=17,
    )

    assert sent["method"] == "POST"
    assert sent["path"] == "/api/visora/prefab/overrides"
    assert sent["instancePath"] == "Level/Crate/Lid"
    assert sent["scenePath"] == ""
    assert sent["includeDefaultOverrides"] is True
    assert sent["scope"] == "outermost"
    assert sent["maxOverrides"] == 17
    # A pure read keeps the default replay-on-timeout policy: no retry_on_timeout=False override.
    assert "retry_on_timeout" not in sent["kwargs"]


@pytest.mark.anyio
async def test_inspect_prefab_overrides_round_trips_a_full_unity_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(_self: object, _method: str, path: str, **_kwargs: Any) -> httpx.Response:
        if path == "/api/visora/info":
            return httpx.Response(200, json={"success": True, "supportedFeatures": ["prefab_override_inspection"]})
        if path == "/api/editor/state":
            return httpx.Response(200, json={"success": True, "isPlaying": False, "isCompiling": False})
        return httpx.Response(200, json=_override_response())

    async def fake_is_native(_self: object, force_refresh: bool = False) -> bool:
        return True

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    monkeypatch.setattr(UnityBridge, "is_native_bridge", fake_is_native)
    monkeypatch.setattr(prefab_pkg, "bridge", UnityBridge())

    result = await inspect_prefab_overrides("Level/Crate/Lid")

    assert result.success is True, result.error
    assert result.instance_root_path == "Level/Crate"
    assert result.total_override_count == 1
    assert result.excluded_default_override_count == 2
    assert result.overrides[0].override_id == "ovr_1a2b3c4d5e6f7a8b"
    assert result.overrides[0].category == "added_component"
    assert result.overrides[0].recommended_target_asset_path == "Assets/Prefabs/Crate.prefab"


@pytest.mark.anyio
async def test_legacy_bridge_gets_unsupported_override_inspection_without_csharp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """There is no execute_code fallback: diffing overrides in ad hoc C# is exactly what the tool replaces."""
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

        async def inspect_prefab_overrides_native(self, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("A legacy bridge has no native prefab override endpoint.")

    monkeypatch.setattr(prefab_pkg, "bridge", _LegacyBridge())

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert "prefab_override_inspection" in (result.error or "")
    assert executed == []


@pytest.mark.anyio
async def test_inspect_prefab_overrides_surfaces_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(_self: object, _method: str, path: str, **_kwargs: Any) -> httpx.Response:
        if path == "/api/visora/info":
            return httpx.Response(200, json={"success": True, "supportedFeatures": ["prefab_override_inspection"]})
        if path == "/api/editor/state":
            return httpx.Response(200, json={"success": True, "isPlaying": False, "isCompiling": False})
        raise BridgeHTTPError(message="Bridge HTTP error 500: boom", status_code=500, response_body="boom")

    async def fake_is_native(_self: object, force_refresh: bool = False) -> bool:
        return True

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    monkeypatch.setattr(UnityBridge, "is_native_bridge", fake_is_native)
    monkeypatch.setattr(prefab_pkg, "bridge", UnityBridge())

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert "Bridge HTTP error 500" in (result.error or "")
    assert result.overrides == []
