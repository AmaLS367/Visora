from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.schemas.asset import (
    AssetSearchResultItem,
    DownloadAndImportAssetResult,
    ImportLocalAssetResult,
    InspectAssetResult,
    InstantiateSceneAssetResult,
    SearchAssetsResult,
)
from backend.tools.asset import operations
from backend.tools.asset.downloader import (
    download_file_stream,
    extract_filename_from_url,
    safe_extract_zip,
    sanitize_filename,
)
from backend.tools.asset.exceptions import (
    DownloadError,
    ZipSlipSecurityError,
)
from backend.tools.asset.operations import (
    download_and_import_asset_op,
    import_local_asset_op,
    inspect_asset_op,
    instantiate_scene_asset_op,
    search_assets_op,
)
from backend.tools.asset.providers import (
    AmbientCGProvider,
    DirectUrlProvider,
    PolyPizzaProvider,
    SketchfabProvider,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_sanitize_filename() -> None:
    assert sanitize_filename("test/model:name?.glb") == "test_model_name_.glb"
    assert sanitize_filename("...valid_name.fbx...") == "valid_name.fbx"
    assert sanitize_filename("   ") == "asset_file"


def test_extract_filename_from_url() -> None:
    url1 = "https://ambientcg.com/get?file=Wood095_1K-PNG.zip"
    assert extract_filename_from_url(url1) == "Wood095_1K-PNG.zip"

    url2 = "https://cdn.example.com/assets/characters/knight.glb"
    assert extract_filename_from_url(url2) == "knight.glb"

    url3 = "https://example.com/path-without-extension"
    assert extract_filename_from_url(url3, default="fallback.glb") == "fallback.glb"


def test_safe_extract_zip_success(tmp_path: Path) -> None:
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("model.obj", "v 0 0 0\n")
        zf.writestr("textures/albedo.png", b"\x89PNG\r\n\x1a\n")
        zf.writestr("__MACOSX/.hidden", "junk")

    dest_dir = tmp_path / "extracted"
    extracted = safe_extract_zip(zip_path, dest_dir)

    assert "model.obj" in extracted
    assert "textures/albedo.png" in extracted
    assert not any("__MACOSX" in e for e in extracted)
    assert (dest_dir / "model.obj").exists()
    assert (dest_dir / "textures/albedo.png").exists()


def test_safe_extract_zip_slip_rejection(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../evil.sh", "#!/bin/bash\necho evil\n")

    dest_dir = tmp_path / "extracted"
    with pytest.raises(ZipSlipSecurityError, match="attempts path traversal outside target directory"):
        safe_extract_zip(zip_path, dest_dir)


@pytest.mark.anyio
async def test_direct_url_provider() -> None:
    provider = DirectUrlProvider()
    items, warns = await provider.search("https://example.com/props/chair.glb")
    assert len(items) == 1
    assert items[0].name == "chair.glb"
    assert items[0].category == "model"
    assert items[0].download_url == "https://example.com/props/chair.glb"
    assert not warns


@pytest.mark.anyio
async def test_ambientcg_provider_search(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_payload = {
        "foundAssets": [
            {
                "assetId": "Metal020",
                "dataType": "Material",
                "displayName": "Metal 020",
                "tags": ["metal", "clean", "silver"],
                "popularityScore": 92.5,
                "previewImage": {
                    "256-PNG": "https://example.com/metal020_256.png",
                },
                "downloadFolders": {
                    "default": {
                        "downloadFiletypeCategories": {
                            "zip": {
                                "downloads": [
                                    {
                                        "attribute": "1K-PNG",
                                        "downloadLink": "https://ambientcg.com/get?file=Metal020_1K-PNG.zip",
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        ]
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return mock_payload

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def get(self, *args: Any, **kwargs: Any) -> MockResponse:
            _ = (args, kwargs)
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockClient())

    provider = AmbientCGProvider()
    items, warns = await provider.search("metal")
    assert len(items) == 1
    assert items[0].id == "ambientcg:Metal020"
    assert items[0].name == "Metal 020"
    assert items[0].category == "material"
    assert items[0].download_url == "https://ambientcg.com/get?file=Metal020_1K-PNG.zip"
    assert items[0].thumbnail_url == "https://example.com/metal020_256.png"
    assert not warns


@pytest.mark.anyio
async def test_sketchfab_provider_search(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_payload = {
        "results": [
            {
                "uid": "abc12345",
                "name": "Fantasy Sword",
                "user": {"displayName": "WeaponSmith"},
                "license": {"label": "CC-BY 4.0"},
                "thumbnails": {"images": [{"url": "https://example.com/thumb.jpg"}]},
                "vertexCount": 1500,
                "faceCount": 2400,
                "animationCount": 1,
            }
        ]
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return mock_payload

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def get(self, *args: Any, **kwargs: Any) -> MockResponse:
            _ = (args, kwargs)
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockClient())

    provider = SketchfabProvider()
    items, warns = await provider.search("sword")
    assert len(items) == 1
    assert items[0].id == "sketchfab:abc12345"
    assert items[0].name == "Fantasy Sword"
    assert items[0].author == "WeaponSmith"
    assert items[0].category == "model"
    assert not warns


@pytest.mark.anyio
async def test_polypizza_search_without_key() -> None:
    provider = PolyPizzaProvider()
    items, warns = await provider.search("chair")
    assert len(items) == 0
    assert any("POLY_PIZZA_API_KEY" in w for w in warns)


@pytest.mark.anyio
async def test_download_size_limit_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "large.glb"

    class MockStreamResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"content-length": "999999999"}

        async def aiter_bytes(self, _chunk_size: int = 65536) -> Any:
            yield b"x" * 100

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        def stream(self, *args: Any, **kwargs: Any) -> Any:
            _ = (args, kwargs)

            class StreamContext:
                async def __aenter__(self) -> MockStreamResponse:
                    return MockStreamResponse()

                async def __aexit__(self, *args: Any) -> None:
                    pass

            return StreamContext()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: MockClient())

    with pytest.raises(DownloadError, match="exceeds maximum permitted limit"):
        await download_file_stream("https://example.com/large.glb", target, max_bytes=1000)


@pytest.mark.anyio
async def test_download_and_import_asset_op(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock paths
    fake_project = tmp_path / "UnityProject"
    fake_assets = fake_project / "Assets"
    fake_assets.mkdir(parents=True)

    async def mock_resolve_paths() -> tuple[Path, Path]:
        return fake_project, fake_assets

    monkeypatch.setattr(operations, "resolve_unity_paths", mock_resolve_paths)

    # Mock download_file_stream writing a small file
    async def mock_download_stream(url: str, target: Path, **kwargs: Any) -> int:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"dummy_model_bytes")
        return 17

    monkeypatch.setattr(operations, "download_file_stream", mock_download_stream)

    # Mock bridge execute_capability
    async def mock_execute_cap(code: str, **kwargs: Any) -> dict[str, Any]:
        if "instantiate" in kwargs.get("native_path", ""):
            return {
                "success": True,
                "game_object_name": "TestProp",
                "game_object_path": "TestProp",
                "instance_id": 999,
            }
        return {
            "success": True,
            "importedObjects": ["Assets/VisoraDownloads/prop.glb"],
        }

    monkeypatch.setattr(operations.bridge, "execute_capability", mock_execute_cap)

    res = await download_and_import_asset_op(
        url="https://example.com/prop.glb",
        target_folder="Assets/VisoraDownloads",
        instantiate_in_scene=True,
    )

    assert res.success is True
    assert res.asset_path == "Assets/VisoraDownloads/prop.glb"
    assert res.instantiated_game_object == "TestProp"
    assert res.instance_id == 999
    assert res.file_size_bytes == 17


@pytest.mark.anyio
async def test_import_local_asset_op(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local_file = tmp_path / "local_prop.fbx"
    local_file.write_bytes(b"sample_fbx_content")

    fake_project = tmp_path / "UnityProject"
    fake_assets = fake_project / "Assets"
    fake_assets.mkdir(parents=True)

    async def mock_resolve_paths() -> tuple[Path, Path]:
        return fake_project, fake_assets

    monkeypatch.setattr(operations, "resolve_unity_paths", mock_resolve_paths)

    async def mock_execute_cap(code: str, **kwargs: Any) -> dict[str, Any]:
        return {"success": True, "importedObjects": ["Assets/Models/local_prop.fbx"]}

    monkeypatch.setattr(operations.bridge, "execute_capability", mock_execute_cap)

    res = await import_local_asset_op(
        source_path=str(local_file),
        target_folder="Assets/Models",
    )

    assert res.success is True
    assert res.asset_path == "Assets/Models/local_prop.fbx"
    assert res.file_size_bytes == len(b"sample_fbx_content")
    assert (fake_assets / "Models" / "local_prop.fbx").exists()


@pytest.mark.anyio
async def test_inspect_asset_op(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_execute_cap(code: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "asset_path": "Assets/Models/robot.glb",
            "asset_type": "GameObject",
            "model_importer_info": {
                "animation_type": "Humanoid",
                "clip_count": 3,
                "material_import_mode": "ImportViaMaterialDescription",
                "import_normals": True,
                "global_scale": 1.0,
                "mesh_compression": "Off",
            },
            "submesh_count": 2,
            "materials": ["Robot_Mat"],
            "textures": ["Robot_Albedo.png"],
            "animation_clips": ["Idle", "Walk", "Run"],
            "hierarchy_tree": ["Root", "Spine", "Head"],
        }

    monkeypatch.setattr(operations.bridge, "execute_capability", mock_execute_cap)

    res = await inspect_asset_op("Assets/Models/robot.glb")
    assert res.success is True
    assert res.asset_path == "Assets/Models/robot.glb"
    assert res.model_importer_info is not None
    assert res.model_importer_info.animation_type == "Humanoid"
    assert res.model_importer_info.clip_count == 3
    assert "Idle" in res.animation_clips
    assert res.submesh_count == 2


@pytest.mark.anyio
async def test_instantiate_scene_asset_op(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_execute_cap(code: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "game_object_name": "Knight",
            "game_object_path": "Characters/Knight",
            "instance_id": 4242,
            "world_position": [1.0, 0.0, 2.5],
        }

    monkeypatch.setattr(operations.bridge, "execute_capability", mock_execute_cap)

    res = await instantiate_scene_asset_op(
        asset_path="Assets/Characters/Knight.prefab",
        position=[1.0, 0.0, 2.5],
    )
    assert res.success is True
    assert res.game_object_name == "Knight"
    assert res.game_object_path == "Characters/Knight"
    assert res.instance_id == 4242
    assert res.world_position == [1.0, 0.0, 2.5]
