from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.bridge.exceptions import BridgeError
from backend.schemas.asset import (
    DownloadAndImportAssetResult,
    ImportLocalAssetResult,
    InspectAssetResult,
    InstantiateSceneAssetResult,
    SearchAssetsResult,
)
from backend.tools import asset
from backend.tools.asset import operations


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeAssetBridge:
    def __init__(
        self,
        is_native: bool = False,
        native_paths: dict[str, Any] | None = None,
        execute_result: dict[str, Any] | None = None,
        should_fail: bool = False,
    ) -> None:
        self._is_native = is_native
        self.native_paths = native_paths or {
            "success": True,
            "dataPath": "/MockProject/Assets",
            "projectPath": "/MockProject",
        }
        self.execute_result = execute_result or {"success": True}
        self.should_fail = should_fail
        self.executed_calls: list[dict[str, Any]] = []

    async def is_native_bridge(self) -> bool:
        if self.should_fail:
            raise BridgeError("Bridge connection refused")
        return self._is_native

    async def get_project_paths_native(self) -> dict[str, Any]:
        if self.should_fail:
            raise BridgeError("Bridge connection refused")
        return self.native_paths

    async def execute_code(self, code: str) -> dict[str, Any]:
        if self.should_fail:
            raise BridgeError("Bridge connection refused")
        self.executed_calls.append({"type": "code", "code": code})
        return self.execute_result

    async def execute_capability(
        self,
        legacy_code: str,
        *,
        native_path: str | None = None,
        native_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.should_fail:
            raise BridgeError("Bridge connection refused")
        self.executed_calls.append(
            {
                "type": "capability",
                "legacy_code": legacy_code,
                "native_path": native_path,
                "native_payload": native_payload,
            }
        )
        return self.execute_result


@pytest.mark.anyio
async def test_search_assets_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    # Direct URL search
    res = await asset.search_assets("https://example.com/tree.glb")
    assert isinstance(res, SearchAssetsResult)
    assert res.success is True
    assert res.total_count == 1
    assert res.items[0].name == "tree.glb"


@pytest.mark.anyio
async def test_download_and_import_asset_native(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_project = tmp_path / "MockUnity"
    fake_assets = fake_project / "Assets"
    fake_assets.mkdir(parents=True)

    fake_bridge = FakeAssetBridge(
        is_native=True,
        native_paths={
            "success": True,
            "dataPath": str(fake_assets),
            "projectPath": str(fake_project),
        },
        execute_result={
            "success": True,
            "importedObjects": ["Assets/VisoraDownloads/prop.obj"],
            "game_object_name": "PropObject",
            "instance_id": 101,
        },
    )
    monkeypatch.setattr(operations, "bridge", fake_bridge)

    async def mock_download_stream(url: str, target: Path, **kwargs: Any) -> int:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mock_obj_data")
        return 13

    monkeypatch.setattr(operations, "download_file_stream", mock_download_stream)

    res = await asset.download_and_import_asset(
        url="https://example.com/prop.obj",
        target_folder="Assets/VisoraDownloads",
        instantiate_in_scene=True,
    )

    assert isinstance(res, DownloadAndImportAssetResult)
    assert res.success is True
    assert res.asset_path == "Assets/VisoraDownloads/prop.obj"
    assert res.instantiated_game_object == "PropObject"
    assert res.instance_id == 101
    assert len(fake_bridge.executed_calls) >= 2  # import and instantiate


@pytest.mark.anyio
async def test_import_local_asset_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_project = tmp_path / "MockUnity"
    fake_assets = fake_project / "Assets"
    fake_assets.mkdir(parents=True)

    source_file = tmp_path / "imported_model.glb"
    source_file.write_bytes(b"sample_glb_data")

    fake_bridge = FakeAssetBridge(
        is_native=False,
        execute_result={
            "success": True,
            "importedObjects": ["Assets/Imports/imported_model.glb"],
        },
    )
    monkeypatch.setattr(operations, "bridge", fake_bridge)

    async def mock_resolve_paths() -> tuple[Path, Path]:
        return fake_project, fake_assets

    monkeypatch.setattr(operations, "resolve_unity_paths", mock_resolve_paths)

    res = await asset.import_local_asset(
        source_path=str(source_file),
        target_folder="Assets/Imports",
        instantiate_in_scene=False,
    )

    assert isinstance(res, ImportLocalAssetResult)
    assert res.success is True
    assert res.asset_path == "Assets/Imports/imported_model.glb"
    assert (fake_assets / "Imports" / "imported_model.glb").exists()


@pytest.mark.anyio
async def test_inspect_imported_asset_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeAssetBridge(
        execute_result={
            "success": True,
            "asset_path": "Assets/Characters/Hero.fbx",
            "asset_type": "GameObject",
            "model_importer_info": {
                "animation_type": "Generic",
                "clip_count": 1,
                "material_import_mode": "None",
                "import_normals": True,
                "global_scale": 1.0,
                "mesh_compression": "Off",
            },
            "submesh_count": 1,
            "materials": ["HeroMat"],
            "textures": [],
            "animation_clips": ["HeroWalk"],
            "hierarchy_tree": ["Root", "Body"],
        }
    )
    monkeypatch.setattr(operations, "bridge", fake_bridge)

    res = await asset.inspect_imported_asset("Assets/Characters/Hero.fbx")
    assert isinstance(res, InspectAssetResult)
    assert res.success is True
    assert res.asset_type == "GameObject"
    assert res.model_importer_info is not None
    assert res.model_importer_info.animation_type == "Generic"
    assert "HeroWalk" in res.animation_clips


@pytest.mark.anyio
async def test_instantiate_scene_asset_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeAssetBridge(
        execute_result={
            "success": True,
            "game_object_name": "HeroInstance",
            "game_object_path": "HeroInstance",
            "instance_id": 777,
            "world_position": [0.0, 5.0, 0.0],
        }
    )
    monkeypatch.setattr(operations, "bridge", fake_bridge)

    res = await asset.instantiate_scene_asset(
        asset_path="Assets/Characters/Hero.prefab",
        position=[0.0, 5.0, 0.0],
    )
    assert isinstance(res, InstantiateSceneAssetResult)
    assert res.success is True
    assert res.game_object_name == "HeroInstance"
    assert res.instance_id == 777
    assert res.world_position == [0.0, 5.0, 0.0]


@pytest.mark.anyio
async def test_inspect_and_instantiate_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    failing_bridge = FakeAssetBridge(should_fail=True)
    monkeypatch.setattr(operations, "bridge", failing_bridge)

    inspect_res = await asset.inspect_imported_asset("Assets/Missing.fbx")
    assert isinstance(inspect_res, InspectAssetResult)
    assert inspect_res.success is False
    assert "Bridge connection refused" in (inspect_res.error or "")

    inst_res = await asset.instantiate_scene_asset("Assets/Missing.prefab")
    assert isinstance(inst_res, InstantiateSceneAssetResult)
    assert inst_res.success is False
    assert "Bridge connection refused" in (inst_res.error or "")
