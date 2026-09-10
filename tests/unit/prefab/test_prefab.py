from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

import backend.tools.prefab as prefab_pkg
from backend.bridge import BridgeBusyError, BridgeConnectionError
from backend.config import get_settings
from backend.schemas.prefab import (
    InspectPrefabAssetResult,
    PrefabComponentInfo,
    PrefabNestedInstance,
    PrefabObjectNode,
)
from backend.tools.prefab.inspection import _normalize_asset_path, inspect_prefab_asset

_CAPABILITY = "prefab_asset_inspection"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _native_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": True,
        "assetPath": "Assets/Prefabs/Enemy.prefab",
        "prefabName": "Enemy",
        "assetGuid": "3f1c0d8e",
        "prefabKind": "variant",
        "basePrefabPath": "Assets/Prefabs/Character.prefab",
        "rootObjectName": "Enemy",
        "rootConnectionStatus": "connected",
        "hierarchy": [
            {
                "relativePath": "",
                "name": "Enemy",
                "depth": 0,
                "activeSelf": True,
                "components": [
                    {"typeName": "Transform", "isMissingScript": False},
                    {"typeName": "MissingScript", "isMissingScript": True},
                ],
                "isNestedPrefabInstanceRoot": False,
                "nestedSourceAssetPath": None,
            },
            {
                "relativePath": "Weapon",
                "name": "Weapon",
                "depth": 1,
                "activeSelf": False,
                "components": [{"typeName": "Transform", "isMissingScript": False}],
                "isNestedPrefabInstanceRoot": True,
                "nestedSourceAssetPath": "Assets/Prefabs/Sword.prefab",
            },
        ],
        "nestedPrefabs": [
            {
                "relativePath": "Weapon",
                "name": "Weapon",
                "sourceAssetPath": "Assets/Prefabs/Sword.prefab",
                "sourceGuid": "aa11bb22",
                "connectionStatus": "connected",
            }
        ],
        "editTargetAssetPaths": [
            "Assets/Prefabs/Character.prefab",
            "Assets/Prefabs/Enemy.prefab",
            "Assets/Prefabs/Sword.prefab",
        ],
        "totalObjectCount": 2,
        "totalComponentCount": 3,
        "truncated": False,
        "warnings": [],
    }
    payload.update(overrides)
    return payload


class _FakePrefabBridge:
    def __init__(
        self,
        *,
        supported_features: set[str] | None = None,
        response: dict[str, Any] | None = None,
        raises: Exception | None = None,
        editor_state: dict[str, Any] | None = None,
        editor_state_raises: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.ready_waits = 0
        self._supported_features = supported_features if supported_features is not None else {_CAPABILITY}
        self._raises = raises
        self._editor_state = editor_state or {"isPlaying": False, "isCompiling": False, "isUpdating": False}
        self._editor_state_raises = editor_state_raises
        self.response = response if response is not None else _native_payload()

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def wait_for_editor_ready(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        del timeout_seconds
        self.ready_waits += 1
        if self._editor_state_raises is not None:
            raise self._editor_state_raises
        return self._editor_state

    async def inspect_prefab_asset_native(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self.response


# --------------------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------------------


def test_prefab_schemas_accept_a_full_result() -> None:
    node = PrefabObjectNode(
        relative_path="Arm/Hand",
        name="Hand",
        depth=2,
        active_self=True,
        components=[PrefabComponentInfo(type_name="Transform")],
    )
    assert node.is_nested_prefab_instance_root is False
    assert node.nested_source_asset_path is None
    assert node.components[0].is_missing_script is False

    nested = PrefabNestedInstance(
        relative_path="Arm/Hand",
        name="Hand",
        source_asset_path="Assets/Prefabs/Hand.prefab",
        source_guid="deadbeef",
        connection_status="connected",
    )

    result = InspectPrefabAssetResult(
        success=True,
        asset_path="Assets/Prefabs/Enemy.prefab",
        prefab_name="Enemy",
        guid="3f1c0d8e",
        prefab_kind="variant",
        base_prefab_path="Assets/Prefabs/Character.prefab",
        root_object_name="Enemy",
        root_connection_status="connected",
        hierarchy=[node],
        nested_prefabs=[nested],
        edit_target_asset_paths=["Assets/Prefabs/Character.prefab"],
        total_object_count=1,
        total_component_count=1,
    )
    assert result.truncated is False
    assert result.warnings == []


def test_prefab_schemas_reject_unknown_vocabulary() -> None:
    with pytest.raises(ValidationError):
        InspectPrefabAssetResult(
            success=True,
            asset_path="Assets/A.prefab",
            prefab_kind="nested",  # type: ignore[arg-type]
        )

    with pytest.raises(ValidationError):
        PrefabNestedInstance(
            relative_path="A",
            name="A",
            connection_status="detached",  # type: ignore[arg-type]
        )

    with pytest.raises(ValidationError):
        PrefabObjectNode(name="A")  # type: ignore[call-arg]


# --------------------------------------------------------------------------------------
# Path validation
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Assets\\Prefabs\\Enemy.prefab", "Assets/Prefabs/Enemy.prefab"),
        ("  Assets/Prefabs/Enemy.prefab  ", "Assets/Prefabs/Enemy.prefab"),
        ("Assets//Prefabs///Enemy.prefab", "Assets/Prefabs/Enemy.prefab"),
        ("Packages/com.acme.kit/Runtime/Rig.prefab", "Packages/com.acme.kit/Runtime/Rig.prefab"),
        ("Assets/Models/Hero.FBX", "Assets/Models/Hero.FBX"),
    ],
)
def test_normalize_asset_path_accepts_project_prefabs(raw: str, expected: str) -> None:
    clean, error = _normalize_asset_path(raw)
    assert error is None
    assert clean == expected


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("", "required"),
        ("   ", "required"),
        ("/home/user/Enemy.prefab", "project-relative"),
        ("C:/Unity/Enemy.prefab", "project-relative"),
        ("Assets/../../etc/passwd.prefab", "traverse"),
        ("Library/Enemy.prefab", "Assets/ or Packages/"),
        ("Assets/Materials/Plain.mat", "not a Prefab-compatible asset"),
        ("Assets/Prefabs/Enemy", "not a Prefab-compatible asset"),
    ],
)
def test_normalize_asset_path_rejects_everything_else(raw: str, fragment: str) -> None:
    _clean, error = _normalize_asset_path(raw)
    assert error is not None
    assert fragment in error


# --------------------------------------------------------------------------------------
# Tool behavior
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_inspect_prefab_asset_maps_native_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge()
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets\\Prefabs\\Enemy.prefab")

    assert result.success is True
    assert result.error is None
    assert result.asset_path == "Assets/Prefabs/Enemy.prefab"
    assert result.prefab_kind == "variant"
    assert result.guid == "3f1c0d8e"
    assert result.base_prefab_path == "Assets/Prefabs/Character.prefab"
    assert result.root_connection_status == "connected"
    assert [node.relative_path for node in result.hierarchy] == ["", "Weapon"]
    assert result.hierarchy[0].components[1].is_missing_script is True
    assert result.hierarchy[1].active_self is False
    assert result.hierarchy[1].nested_source_asset_path == "Assets/Prefabs/Sword.prefab"
    assert result.nested_prefabs[0].source_asset_path == "Assets/Prefabs/Sword.prefab"
    assert result.nested_prefabs[0].connection_status == "connected"
    assert result.edit_target_asset_paths == [
        "Assets/Prefabs/Character.prefab",
        "Assets/Prefabs/Enemy.prefab",
        "Assets/Prefabs/Sword.prefab",
    ]
    assert result.total_object_count == 2
    assert result.total_component_count == 3
    assert result.truncated is False

    assert bridge.ready_waits == 1
    assert bridge.calls == [
        {"asset_path": "Assets/Prefabs/Enemy.prefab", "max_objects": get_settings().prefab_max_hierarchy_nodes}
    ]


@pytest.mark.anyio
async def test_inspect_prefab_asset_rejects_a_non_prefab_path_before_touching_the_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _FakePrefabBridge()
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Materials/Plain.mat")

    assert result.success is False
    assert "not a Prefab-compatible asset" in (result.error or "")
    assert result.asset_path == "Assets/Materials/Plain.mat"
    assert bridge.calls == []
    assert bridge.ready_waits == 0


@pytest.mark.anyio
async def test_inspect_prefab_asset_reports_unsupported_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(supported_features=set())
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert _CAPABILITY in (result.error or "")
    assert bridge.calls == []


@pytest.mark.anyio
async def test_inspect_prefab_asset_requires_edit_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(editor_state={"isPlaying": True})
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert "Edit Mode" in (result.error or "")
    assert bridge.calls == []


@pytest.mark.anyio
async def test_inspect_prefab_asset_surfaces_a_busy_editor_as_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(
        editor_state_raises=BridgeBusyError(
            message="Unity Editor is compiling scripts", reason="compiling", retry_after_seconds=3.0
        )
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert result.retryable is True
    assert result.unity_state == "compiling"
    assert result.retry_after_seconds == 3.0
    assert bridge.calls == []


@pytest.mark.anyio
async def test_inspect_prefab_asset_surfaces_bridge_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(raises=BridgeConnectionError(message="bridge unreachable", ports=[7890]))
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert "Bridge call failed" in (result.error or "")
    assert result.asset_path == "Assets/Prefabs/Enemy.prefab"


@pytest.mark.anyio
async def test_inspect_prefab_asset_never_fakes_success_on_a_unity_error(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(
        response={
            "success": False,
            "assetPath": "Assets/Prefabs/Enemy.prefab",
            "error": "Asset not found at path: Assets/Prefabs/Enemy.prefab",
            "warnings": ["stale import"],
        }
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert "Asset not found" in (result.error or "")
    assert result.warnings == ["stale import"]
    assert result.hierarchy == []


@pytest.mark.anyio
async def test_inspect_prefab_asset_rejects_a_successful_but_empty_hierarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(response=_native_payload(hierarchy=[]))
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is False
    assert "no Prefab hierarchy" in (result.error or "")


@pytest.mark.anyio
async def test_inspect_prefab_asset_propagates_unity_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(
        response=_native_payload(truncated=True, totalObjectCount=4096, warnings=["Prefab contains 4096 GameObjects"])
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is True
    assert result.truncated is True
    assert result.total_object_count == 4096
    assert result.warnings == ["Prefab contains 4096 GameObjects"]


@pytest.mark.anyio
async def test_inspect_prefab_asset_caps_an_oversized_bridge_response(monkeypatch: pytest.MonkeyPatch) -> None:
    oversized = [
        {
            "relativePath": f"Child{index}",
            "name": f"Child{index}",
            "depth": 1,
            "activeSelf": True,
            "components": [],
        }
        for index in range(get_settings().prefab_max_hierarchy_nodes + 5)
    ]
    bridge = _FakePrefabBridge(response=_native_payload(hierarchy=oversized, truncated=False))
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is True
    assert result.truncated is True
    assert len(result.hierarchy) == get_settings().prefab_max_hierarchy_nodes
    assert any("capped locally" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_inspect_prefab_asset_coerces_unknown_vocabulary(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(
        response=_native_payload(
            prefabKind="brand-new-kind",
            rootConnectionStatus="entangled",
            nestedPrefabs=[
                {
                    "relativePath": "Weapon",
                    "name": "Weapon",
                    "sourceAssetPath": "Assets/Prefabs/Sword.prefab",
                    "sourceGuid": "aa11bb22",
                    "connectionStatus": "quantum",
                }
            ],
        )
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is True
    assert result.prefab_kind == "unknown"
    assert result.root_connection_status == "unknown"
    assert result.nested_prefabs[0].connection_status == "unknown"
    assert any("brand-new-kind" in warning for warning in result.warnings)
    assert any("quantum" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_inspect_prefab_asset_ignores_malformed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(
        response=_native_payload(
            hierarchy=[
                "not-a-node",
                {
                    "relativePath": "",
                    "name": "Enemy",
                    "depth": 0,
                    "activeSelf": True,
                    "components": ["not-a-component", {"typeName": "Transform"}],
                },
            ],
            nestedPrefabs=["not-a-nested-instance"],
        )
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is True
    assert len(result.hierarchy) == 1
    assert [component.type_name for component in result.hierarchy[0].components] == ["Transform"]
    assert result.nested_prefabs == []
    assert any("malformed" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_inspect_prefab_asset_maps_model_prefab_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakePrefabBridge(
        response=_native_payload(
            assetPath="Assets/Models/Hero.fbx",
            prefabName="Hero",
            prefabKind="model",
            basePrefabPath=None,
            rootObjectName="Hero",
            rootConnectionStatus="not_an_instance",
            editTargetAssetPaths=[],
            warnings=["Model Prefabs are read-only."],
        )
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Models/Hero.fbx")

    assert result.success is True
    assert result.prefab_kind == "model"
    assert result.prefab_name == "Hero"
    assert result.base_prefab_path is None
    assert result.root_connection_status == "not_an_instance"
    assert result.edit_target_asset_paths == []
    assert "Model Prefabs are read-only." in result.warnings


@pytest.mark.anyio
async def test_inspect_prefab_asset_handles_broken_variant_and_missing_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _FakePrefabBridge(
        response=_native_payload(
            prefabKind="variant",
            rootConnectionStatus="missing_asset",
            basePrefabPath=None,
            nestedPrefabs=[
                {
                    "relativePath": "Weapon",
                    "name": "Weapon",
                    "sourceAssetPath": None,
                    "sourceGuid": None,
                    "connectionStatus": "missing_asset",
                }
            ],
            editTargetAssetPaths=["Assets/Prefabs/Enemy.prefab"],
            warnings=["The base Prefab of this Variant is missing."],
        )
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is True
    assert result.prefab_kind == "variant"
    assert result.root_connection_status == "missing_asset"
    assert result.base_prefab_path is None
    assert result.nested_prefabs[0].connection_status == "missing_asset"
    assert result.nested_prefabs[0].source_asset_path is None
    assert result.edit_target_asset_paths == ["Assets/Prefabs/Enemy.prefab"]


@pytest.mark.anyio
async def test_inspect_prefab_asset_handles_non_list_and_malformed_scalar_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _FakePrefabBridge(
        response={
            "success": True,
            "assetPath": "Assets/Prefabs/Enemy.prefab",
            "hierarchy": [
                {
                    "relativePath": "",
                    "name": "Enemy",
                    "depth": "not-an-int",
                    "activeSelf": True,
                    "components": "not-a-list",
                }
            ],
            "nestedPrefabs": "not-a-list",
            "editTargetAssetPaths": "not-a-list",
            "totalObjectCount": "invalid-count",
            "totalComponentCount": "invalid-count",
        }
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Enemy.prefab")

    assert result.success is True
    assert len(result.hierarchy) == 1
    assert result.hierarchy[0].depth == 0
    assert result.hierarchy[0].components == []
    assert result.nested_prefabs == []
    assert result.edit_target_asset_paths == []
    assert result.total_object_count == 1
    assert result.total_component_count == 0


@pytest.mark.anyio
async def test_inspect_prefab_asset_preserves_disambiguated_sibling_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _FakePrefabBridge(
        response=_native_payload(
            hierarchy=[
                {"relativePath": "", "name": "Robot", "depth": 0, "activeSelf": True, "components": []},
                {"relativePath": "Arm[0]", "name": "Arm", "depth": 1, "activeSelf": True, "components": []},
                {"relativePath": "Arm[0]/Hand", "name": "Hand", "depth": 2, "activeSelf": True, "components": []},
                {"relativePath": "Arm[1]", "name": "Arm", "depth": 1, "activeSelf": True, "components": []},
                {"relativePath": "Arm[1]/Hand", "name": "Hand", "depth": 2, "activeSelf": True, "components": []},
            ],
            warnings=["GameObject 'Robot' has multiple children named 'Arm'; paths are disambiguated with indices."],
        )
    )
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)

    result = await inspect_prefab_asset("Assets/Prefabs/Robot.prefab")

    assert result.success is True
    assert [node.relative_path for node in result.hierarchy] == [
        "",
        "Arm[0]",
        "Arm[0]/Hand",
        "Arm[1]",
        "Arm[1]/Hand",
    ]
    assert any("disambiguated with indices" in w for w in result.warnings)
