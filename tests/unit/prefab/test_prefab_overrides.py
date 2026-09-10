from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

import backend.tools.prefab as prefab_pkg
from backend.bridge import BridgeBusyError, BridgeConnectionError, BridgeTimeoutError
from backend.schemas.prefab import InspectPrefabOverridesResult, PrefabOverride, PrefabOverrideCounts
from backend.tools.prefab.common import normalize_hierarchy_path, optional_asset_path
from backend.tools.prefab.overrides import inspect_prefab_overrides

_CAPABILITY = "prefab_override_inspection"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _entry(override_id: str, category: str, **fields: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "overrideId": override_id,
        "category": category,
        "objectPath": "",
        "sourceObjectPath": "",
        "componentType": None,
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
        "description": f"{category} change",
    }
    entry.update(fields)
    return entry


def _all_categories() -> list[dict[str, Any]]:
    return [
        _entry(
            "ovr_0000000000000001",
            "modified_property",
            objectPath="Lid",
            sourceObjectPath="Lid",
            componentType="BoxCollider",
            componentOrdinal=1,
            propertyPath="m_Size.x",
            sourceValue={"kind": "float", "value": 1.0},
            instanceValue={"kind": "float", "value": 2.5},
            description="'Lid' BoxCollider[1]: 'm_Size.x' changed from 1 to 2.5.",
        ),
        _entry(
            "ovr_0000000000000002",
            "modified_property",
            objectPath="Body",
            sourceObjectPath="Body",
            componentType="MeshFilter",
            propertyPath="m_Mesh",
            sourceValue={"kind": "object_reference", "value": None, "objectReference": {"isNull": True}},
            instanceValue={
                "kind": "object_reference",
                "value": None,
                "objectReference": {
                    "isNull": False,
                    "typeName": "Mesh",
                    "name": "Dented",
                    "assetPath": "Assets\\Meshes\\Dented.asset",
                    "assetGuid": "c0ffee",
                    "localFileId": 4300000,
                    "scenePath": None,
                    "hierarchyPath": None,
                },
            },
        ),
        _entry(
            "ovr_0000000000000003",
            "added_component",
            objectPath="Lid",
            sourceObjectPath="Lid",
            componentType="SphereCollider",
        ),
        _entry(
            "ovr_0000000000000004",
            "removed_component",
            objectPath="Body",
            sourceObjectPath="Body",
            componentType="MeshRenderer",
        ),
        _entry("ovr_0000000000000005", "added_game_object", objectPath="Extra", sourceObjectPath=None),
        _entry(
            "ovr_0000000000000006",
            "removed_game_object",
            objectPath="",
            sourceObjectPath="Handle",
            targetAssetPaths=["Assets/Prefabs/Crate.prefab", "Assets/Prefabs/Box.prefab"],
        ),
    ]


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
        "totalOverrideCount": 6,
        "overrideCounts": {
            "modifiedProperty": 2,
            "addedComponent": 1,
            "removedComponent": 1,
            "addedGameObject": 1,
            "removedGameObject": 1,
        },
        "excludedDefaultOverrideCount": 2,
        "truncated": False,
        "overrides": _all_categories(),
        "pathCandidates": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


class _FakeOverrideBridge:
    def __init__(
        self,
        *,
        supported_features: set[str] | None = None,
        response: Any = None,
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
        self.response = response if response is not None else _payload()

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def wait_for_editor_ready(self, timeout_seconds: float = 15.0) -> dict[str, Any]:
        del timeout_seconds
        self.ready_waits += 1
        if self._editor_state_raises is not None:
            raise self._editor_state_raises
        return self._editor_state

    async def inspect_prefab_overrides_native(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        # A fresh copy per call, like a real HTTP response, so tests can compare repeated calls.
        return copy.deepcopy(self.response)


def _install(monkeypatch: pytest.MonkeyPatch, bridge: _FakeOverrideBridge) -> _FakeOverrideBridge:
    monkeypatch.setattr(prefab_pkg, "bridge", bridge)
    return bridge


# --------------------------------------------------------------------------------------
# Schemas and path normalization
# --------------------------------------------------------------------------------------


def test_override_schemas_reject_unknown_vocabulary() -> None:
    with pytest.raises(ValidationError):
        PrefabOverride(override_id="ovr_0000000000000001", category="renamed")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        InspectPrefabOverridesResult(success=True, instance_path="A", scope="innermost")  # type: ignore[arg-type]


def test_override_counts_total_sums_every_category() -> None:
    counts = PrefabOverrideCounts(
        modified_property=3, added_component=1, removed_component=2, added_game_object=4, removed_game_object=5
    )
    assert counts.total() == 15


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Level/Crate/Lid", "Level/Crate/Lid"),
        ("  /Level/Crate/  ", "Level/Crate"),
        ("Level/Arm[1]/Hand", "Level/Arm[1]/Hand"),
        ("Level/Name With Spaces", "Level/Name With Spaces"),
    ],
)
def test_normalize_hierarchy_path_accepts_rooted_paths(raw: str, expected: str) -> None:
    clean, error = normalize_hierarchy_path(raw)
    assert error is None
    assert clean == expected


@pytest.mark.parametrize(("raw", "fragment"), [("", "required"), ("  / ", "required"), ("A//B", "empty segment")])
def test_normalize_hierarchy_path_rejects_malformed_paths(raw: str, fragment: str) -> None:
    _clean, error = normalize_hierarchy_path(raw)
    assert error is not None
    assert fragment in error


# --------------------------------------------------------------------------------------
# Successful mapping
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_maps_every_override_category(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _install(monkeypatch, _FakeOverrideBridge())

    result = await inspect_prefab_overrides("/Level/Crate/Lid/", scene_path="Assets\\Scenes\\Main.unity")

    assert result.success is True, result.error
    assert result.instance_path == "Level/Crate/Lid"
    assert result.scene_path == "Assets/Scenes/Main.unity"
    assert result.instance_root_path == "Level/Crate"
    assert result.outermost_instance_root_path == "Level/Crate"
    assert result.scope == "nearest"
    assert result.source_asset_path == "Assets/Prefabs/Crate.prefab"
    assert result.source_guid == "abc123"
    assert result.prefab_kind == "regular"
    assert result.connection_status == "connected"
    assert result.total_override_count == 6
    assert result.excluded_default_override_count == 2
    assert result.override_counts.model_dump() == {
        "modified_property": 2,
        "added_component": 1,
        "removed_component": 1,
        "added_game_object": 1,
        "removed_game_object": 1,
    }
    assert [entry.category for entry in result.overrides] == [
        "modified_property",
        "modified_property",
        "added_component",
        "removed_component",
        "added_game_object",
        "removed_game_object",
    ]

    size = result.overrides[0]
    assert size.component_type == "BoxCollider"
    assert size.component_ordinal == 1
    assert size.property_path == "m_Size.x"
    assert size.source_value is not None
    assert size.source_value.kind == "float"
    assert size.source_value.value == 1.0
    assert size.instance_value is not None
    assert size.instance_value.value == 2.5
    assert size.applicable is True
    assert size.recommended_target_asset_path == "Assets/Prefabs/Crate.prefab"

    mesh = result.overrides[1]
    assert mesh.source_value is not None
    assert mesh.source_value.object_reference is not None
    assert mesh.source_value.object_reference.is_null is True
    assert mesh.instance_value is not None
    reference = mesh.instance_value.object_reference
    assert reference is not None
    assert reference.asset_path == "Assets/Meshes/Dented.asset"
    assert reference.guid == "c0ffee"
    assert reference.local_file_id == 4300000
    assert reference.type_name == "Mesh"

    assert result.overrides[4].source_object_path is None
    # Target order is the source chain (immediate source inwards) and must not be re-sorted.
    assert result.overrides[5].target_asset_paths == ["Assets/Prefabs/Crate.prefab", "Assets/Prefabs/Box.prefab"]

    assert bridge.ready_waits == 1
    assert bridge.calls == [
        {
            "instance_path": "Level/Crate/Lid",
            "scene_path": "Assets/Scenes/Main.unity",
            "include_default_overrides": False,
            "scope": "nearest",
            "max_overrides": 200,
        }
    ]


@pytest.mark.anyio
async def test_repeated_calls_return_identical_ids_and_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeOverrideBridge())

    first = await inspect_prefab_overrides("Level/Crate/Lid")
    second = await inspect_prefab_overrides("Level/Crate/Lid")

    assert [entry.override_id for entry in first.overrides] == [f"ovr_000000000000000{index}" for index in range(1, 7)]
    assert first.model_dump() == second.model_dump()


@pytest.mark.anyio
@pytest.mark.parametrize("scope", ["nearest", "outermost"])
async def test_scope_is_forwarded_and_echoed(monkeypatch: pytest.MonkeyPatch, scope: str) -> None:
    root = "Level/Outer/Inner" if scope == "nearest" else "Level/Outer"
    bridge = _install(
        monkeypatch,
        _FakeOverrideBridge(
            response=_payload(
                scope=scope,
                instanceRootPath=root,
                outermostInstanceRootPath="Level/Outer",
                sourceAssetPath="Assets/Prefabs/Inner.prefab" if scope == "nearest" else "Assets/Prefabs/Outer.prefab",
            )
        ),
    )

    result = await inspect_prefab_overrides("Level/Outer/Inner/Blade", scope=scope)  # type: ignore[arg-type]

    assert result.success is True, result.error
    assert result.scope == scope
    assert result.instance_root_path == root
    assert result.outermost_instance_root_path == "Level/Outer"
    assert bridge.calls[0]["scope"] == scope


@pytest.mark.anyio
async def test_include_default_overrides_keeps_them_flagged_and_non_applicable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default = _entry(
        "ovr_00000000000000d1",
        "modified_property",
        componentType="Transform",
        propertyPath="m_LocalPosition.x",
        sourceValue={"kind": "float", "value": 0.0},
        instanceValue={"kind": "float", "value": 5.0},
        isDefaultOverride=True,
        targetAssetPaths=[],
        recommendedTargetAssetPath=None,
        applicable=False,
        notApplicableReason="Unity classifies this as a default override.",
    )
    counts = {
        "modifiedProperty": 1,
        "addedComponent": 0,
        "removedComponent": 0,
        "addedGameObject": 0,
        "removedGameObject": 0,
    }
    bridge = _install(
        monkeypatch,
        _FakeOverrideBridge(
            response=_payload(
                includeDefaultOverrides=True,
                overrides=[default],
                totalOverrideCount=1,
                overrideCounts=counts,
                excludedDefaultOverrideCount=0,
            )
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate", include_default_overrides=True)

    assert result.success is True, result.error
    assert result.include_default_overrides is True
    assert bridge.calls[0]["include_default_overrides"] is True
    assert result.overrides[0].is_default_override is True
    assert result.overrides[0].applicable is False
    assert "default override" in (result.overrides[0].not_applicable_reason or "")


@pytest.mark.anyio
async def test_default_overrides_leaked_by_the_bridge_are_filtered_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    leaked = _entry(
        "ovr_00000000000000d1",
        "modified_property",
        propertyPath="m_LocalPosition.x",
        isDefaultOverride=True,
        applicable=False,
        targetAssetPaths=[],
        recommendedTargetAssetPath=None,
    )
    overrides = [*_all_categories(), leaked]
    counts = dict(_payload()["overrideCounts"], modifiedProperty=3)
    _install(
        monkeypatch,
        _FakeOverrideBridge(
            response=_payload(
                overrides=overrides, totalOverrideCount=7, overrideCounts=counts, excludedDefaultOverrideCount=0
            )
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is True, result.error
    assert all(not entry.is_default_override for entry in result.overrides)
    assert result.total_override_count == 6
    assert result.override_counts.modified_property == 2
    assert result.excluded_default_override_count == 1
    assert any("default override" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_unity_truncation_keeps_real_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        _FakeOverrideBridge(
            response=_payload(overrides=_all_categories()[:2], truncated=True, warnings=["Instance has 6 overrides"])
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate", max_overrides=2)

    assert result.success is True, result.error
    assert result.truncated is True
    assert len(result.overrides) == 2
    assert result.total_override_count == 6
    assert result.override_counts.total() == 6
    assert result.warnings == ["Instance has 6 overrides"]


@pytest.mark.anyio
async def test_an_oversized_bridge_response_is_capped_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeOverrideBridge())

    result = await inspect_prefab_overrides("Level/Crate", max_overrides=3)

    assert result.success is True, result.error
    assert result.truncated is True
    assert [entry.override_id for entry in result.overrides] == [
        "ovr_0000000000000001",
        "ovr_0000000000000002",
        "ovr_0000000000000003",
    ]
    assert result.total_override_count == 6
    assert any("capped locally" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_duplicate_ids_are_reported_and_never_addressable(monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = _all_categories()
    overrides[1]["overrideId"] = overrides[0]["overrideId"]
    _install(monkeypatch, _FakeOverrideBridge(response=_payload(overrides=overrides)))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is True, result.error
    collided = [entry for entry in result.overrides if entry.id_collision]
    assert len(collided) == 2
    for entry in collided:
        assert entry.applicable is False
        assert entry.target_asset_paths == []
        assert entry.recommended_target_asset_path is None
        assert "not unique" in (entry.not_applicable_reason or "")
    assert any("appears more than once" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_inconsistent_applicability_is_downgraded_not_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = _all_categories()
    overrides[0].update(targetAssetPaths=[], applicable=True)
    overrides[2].update(recommendedTargetAssetPath="Assets/Prefabs/Elsewhere.prefab")
    overrides[3].update(
        applicable=False, targetAssetPaths=[], recommendedTargetAssetPath=None, notApplicableReason=None
    )
    _install(monkeypatch, _FakeOverrideBridge(response=_payload(overrides=overrides)))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is True, result.error
    assert result.overrides[0].applicable is False
    assert result.overrides[2].recommended_target_asset_path is None
    assert result.overrides[2].applicable is True
    assert result.overrides[3].not_applicable_reason
    assert len(result.warnings) == 2


@pytest.mark.anyio
async def test_unknown_vocabulary_is_coerced_with_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = _all_categories()
    overrides[0]["instanceValue"] = {"kind": "quaternionish", "value": "0,0,0,1"}
    _install(
        monkeypatch,
        _FakeOverrideBridge(
            response=_payload(prefabKind="hologram", connectionStatus="entangled", overrides=overrides)
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is True, result.error
    assert result.prefab_kind == "unknown"
    assert result.connection_status == "unknown"
    assert result.overrides[0].instance_value is not None
    assert result.overrides[0].instance_value.kind == "other"
    assert result.overrides[0].instance_value.value == "0,0,0,1"
    assert any("hologram" in warning for warning in result.warnings)
    assert any("quaternionish" in warning for warning in result.warnings)


# --------------------------------------------------------------------------------------
# Malformed and partial payloads: an incomplete diff is never success=true
# --------------------------------------------------------------------------------------


def _with_entry(index: int, **fields: Any) -> dict[str, Any]:
    overrides = _all_categories()
    overrides[index].update(fields)
    return _payload(overrides=overrides)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "fragment"),
    [
        (_payload(overrides=[*_all_categories()[:5], "not-an-entry"]), "malformed override entr"),
        (_with_entry(0, overrideId="12345"), "invalid override ID"),
        (_with_entry(0, overrideId=None), "invalid override ID"),
        (_with_entry(1, category="renamed_object"), "unknown category"),
        (_with_entry(0, instanceValue={"kind": "float", "value": {"x": 1}}), "not a scalar"),
        (_with_entry(0, sourceValue="1.0"), "not an object"),
        (_with_entry(1, instanceValue={"kind": "object_reference", "objectReference": "Dented"}), "not an object"),
        (_with_entry(2, targetAssetPaths="Assets/Prefabs/Crate.prefab"), "non-list target"),
        (_payload(overrides=None), "no override list"),
        (_payload(overrides="nope"), "no override list"),
        (_payload(instanceRootPath=None), "instance root"),
        (_payload(instanceRootPath=""), "instance root"),
        (_payload(sourceAssetPath=None), "source Prefab asset"),
        (_payload(sourceAssetPath=""), "source Prefab asset"),
        (_payload(totalOverrideCount=None), "totals"),
        (_payload(overrideCounts=None), "totals"),
        (_payload(overrideCounts={"modifiedProperty": 2}), "totals"),
        (_payload(totalOverrideCount=9), "do not add up"),
        (_payload(overrides=_all_categories()[:4]), "inconsistent"),
    ],
)
async def test_malformed_or_partial_payloads_fail_explicitly(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any], fragment: str
) -> None:
    _install(monkeypatch, _FakeOverrideBridge(response=response))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert fragment in (result.error or "")
    assert result.overrides == []


@pytest.mark.anyio
async def test_standalone_id_collision_entry_is_downgraded(monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = _all_categories()
    overrides[0].update(idCollision=True, applicable=True)
    _install(monkeypatch, _FakeOverrideBridge(response=_payload(overrides=overrides)))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is True, result.error
    collided = result.overrides[0]
    assert collided.id_collision is True
    assert collided.applicable is False
    assert collided.target_asset_paths == []
    assert collided.recommended_target_asset_path is None
    assert "not unique" in (collided.not_applicable_reason or "")


def test_optional_asset_path_strips_leading_slashes() -> None:
    assert optional_asset_path("/Assets/Scenes/Main.unity") == "Assets/Scenes/Main.unity"
    assert optional_asset_path("Assets\\Prefabs\\Crate.prefab") == "Assets/Prefabs/Crate.prefab"
    assert optional_asset_path("   /Assets/Test.prefab  ") == "Assets/Test.prefab"
    assert optional_asset_path("/") is None
    assert optional_asset_path(None) is None
    assert optional_asset_path("") is None


@pytest.mark.anyio
async def test_a_non_object_bridge_payload_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeOverrideBridge(response=["not", "an", "object"]))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert "non-object payload" in (result.error or "")


# --------------------------------------------------------------------------------------
# Unity-reported failures
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ambiguous_path_surfaces_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        _FakeOverrideBridge(
            response={
                "success": False,
                "error": "Hierarchy path 'Level/Crate' is ambiguous: it matches 2 GameObjects.",
                "instancePath": "Level/Crate",
                "pathCandidates": [
                    {"scenePath": "Assets/Scenes/Main.unity", "hierarchyPath": "Level/Crate[0]"},
                    {"scenePath": "Assets/Scenes/Main.unity", "hierarchyPath": "Level/Crate[1]"},
                    {"scenePath": "Assets/Scenes/Main.unity"},
                    "garbage",
                ],
                "warnings": [],
            }
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert "ambiguous" in (result.error or "")
    assert [candidate.hierarchy_path for candidate in result.path_candidates] == ["Level/Crate[0]", "Level/Crate[1]"]
    assert result.overrides == []


@pytest.mark.anyio
async def test_missing_source_asset_keeps_the_connection_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        _FakeOverrideBridge(
            response={
                "success": False,
                "error": "The source Prefab asset of instance 'Level/Crate' is missing; Unity cannot compute its overrides.",
                "instanceRootPath": "Level/Crate",
                "connectionStatus": "missing_asset",
                "prefabKind": "unknown",
                "overrides": [],
            }
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert result.connection_status == "missing_asset"
    assert result.instance_root_path == "Level/Crate"
    assert "missing" in (result.error or "")


@pytest.mark.anyio
async def test_unity_error_without_message_is_still_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeOverrideBridge(response={"success": False}))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert result.error == "Prefab override inspection failed."


# --------------------------------------------------------------------------------------
# Input validation, capability, editor state, transport
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"instance_path": ""}, "required"),
        ({"instance_path": "Level//Crate"}, "empty segment"),
        ({"instance_path": "Level/Crate", "scope": "innermost"}, "scope must be"),
        ({"instance_path": "Level/Crate", "max_overrides": 0}, "max_overrides"),
        ({"instance_path": "Level/Crate", "max_overrides": 1001}, "max_overrides"),
        ({"instance_path": "Level/Crate", "max_overrides": True}, "max_overrides"),
        ({"instance_path": "Level/Crate", "max_overrides": "5"}, "max_overrides"),
        ({"instance_path": "Level/Crate", "include_default_overrides": "yes"}, "include_default_overrides"),
    ],
)
async def test_invalid_input_is_rejected_before_touching_the_bridge(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], fragment: str
) -> None:
    bridge = _install(monkeypatch, _FakeOverrideBridge())

    result = await inspect_prefab_overrides(**kwargs)

    assert result.success is False
    assert fragment in (result.error or "")
    assert bridge.calls == []
    assert bridge.ready_waits == 0


@pytest.mark.anyio
async def test_unsupported_capability_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _install(monkeypatch, _FakeOverrideBridge(supported_features={"prefab_asset_inspection"}))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert _CAPABILITY in (result.error or "")
    assert bridge.calls == []
    assert bridge.ready_waits == 0


@pytest.mark.anyio
async def test_play_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _install(monkeypatch, _FakeOverrideBridge(editor_state={"isPlaying": True}))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert "Edit Mode" in (result.error or "")
    assert bridge.calls == []


@pytest.mark.anyio
async def test_a_busy_editor_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _install(
        monkeypatch,
        _FakeOverrideBridge(
            editor_state_raises=BridgeBusyError(
                message="Unity Editor is compiling scripts", reason="compiling", retry_after_seconds=3.0
            )
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert result.retryable is True
    assert result.unity_state == "compiling"
    assert result.retry_after_seconds == 3.0
    assert bridge.calls == []


@pytest.mark.anyio
async def test_transport_failure_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeOverrideBridge(raises=BridgeConnectionError(message="bridge unreachable", ports=[7890])))

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert "Bridge call failed" in (result.error or "")
    assert "bridge unreachable" in (result.error or "")
    assert result.instance_path == "Level/Crate"
    assert result.overrides == []


@pytest.mark.anyio
async def test_timeout_is_surfaced_without_retry_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        _FakeOverrideBridge(
            raises=BridgeTimeoutError(
                message="Bridge request to '/api/visora/prefab/overrides' timed out after 10.0s.", timeout_seconds=10.0
            )
        ),
    )

    result = await inspect_prefab_overrides("Level/Crate")

    assert result.success is False
    assert result.retryable is False
    assert "timed out after 10.0s" in (result.error or "")
