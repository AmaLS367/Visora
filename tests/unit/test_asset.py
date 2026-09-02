from __future__ import annotations

import io
import socket
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import TypeAdapter, ValidationError

from backend.schemas.asset import (
    AssetSearchResultItem,
    DownloadAndImportAssetResult,
    ImportLocalAssetResult,
    InspectAssetResult,
    InstantiateSceneAssetResult,
    SearchAssetsResult,
    Vector3,
)
from backend.tools.asset import helpers, operations
from backend.tools.asset.downloader import (
    download_file_stream,
    extract_filename_from_url,
    safe_extract_zip,
    sanitize_filename,
    validate_remote_url,
    validate_unitypackage_contents,
)
from backend.tools.asset.exceptions import (
    ArchiveLimitError,
    AssetSecurityError,
    DownloadError,
    ZipSlipSecurityError,
)
from backend.tools.asset.operations import (
    download_and_import_asset,
    import_local_asset,
    inspect_imported_asset,
    instantiate_scene_asset,
    search_assets,
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
    assert not dest_dir.exists()


def test_safe_extract_zip_rejects_archive_with_no_supported_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script_zip = tmp_path / "script.zip"
    with zipfile.ZipFile(script_zip, "w") as zf:
        zf.writestr("Editor/Evil.cs", "class Evil {}")
    # An unsupported extension is skipped rather than aborting the whole archive (see below), so
    # an archive containing *only* unsupported files fails on the "nothing left to extract" check.
    with pytest.raises(AssetSecurityError, match="does not contain any supported asset files"):
        safe_extract_zip(script_zip, tmp_path / "script-out")

    bomb_zip = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("model.obj", "0" * 100_000)

    class ArchiveSettings:
        max_asset_archive_entries = 10_000
        max_asset_archive_entry_size_bytes = 250_000_000
        max_asset_archive_uncompressed_size_bytes = 1_000_000_000
        max_asset_archive_compression_ratio = 2.0

    monkeypatch.setattr("backend.tools.asset.downloader.get_settings", ArchiveSettings)
    with pytest.raises(ArchiveLimitError, match="compression ratio"):
        safe_extract_zip(bomb_zip, tmp_path / "bomb-out")


def test_safe_extract_zip_skips_unsupported_companion_files(tmp_path: Path) -> None:
    """Regression test: every real ambientCG package ships .usdc/.blend/.mtlx/.tres files
    alongside its .png textures. Rejecting the whole archive because of one such sidecar file
    made every ambientCG download fail outright. Supported files must still be extracted, with
    unsupported companions silently skipped rather than aborting the entire import.
    """
    mixed_zip = tmp_path / "Bricks097_1K-PNG.zip"
    with zipfile.ZipFile(mixed_zip, "w") as zf:
        zf.writestr("Bricks097_1K-PNG_Color.png", "not-really-a-png")
        zf.writestr("Bricks097_1K-PNG.usdc", "usd-binary-content")
        zf.writestr("Bricks097_1K-PNG.blend", "blender-binary-content")
        zf.writestr("Bricks097_1K-PNG.mtlx", "<materialx/>")

    extracted = safe_extract_zip(mixed_zip, tmp_path / "mixed-out")

    assert extracted == ["Bricks097_1K-PNG_Color.png"]
    assert not (tmp_path / "mixed-out" / "Bricks097_1K-PNG.usdc").exists()
    assert not (tmp_path / "mixed-out" / "Bricks097_1K-PNG.blend").exists()


def test_safe_extract_zip_keeps_gltf_external_buffer_and_obj_material(tmp_path: Path) -> None:
    """Regression test: .bin and .mtl aren't "assets" on their own, but a non-binary .gltf's
    mesh/skin/bone data lives entirely in its externally referenced .bin buffer, and a .obj's
    material assignment lives in its .mtl. Verified live against a real Sketchfab download: before
    .bin was allow-listed, extraction silently dropped scene.bin and produced a mesh-less, broken
    asset instead of failing loudly - worse than the archive-wide rejection this whole skip-instead
    -of-abort behavior was meant to fix.
    """
    gltf_zip = tmp_path / "character.zip"
    with zipfile.ZipFile(gltf_zip, "w") as zf:
        zf.writestr("scene.gltf", '{"buffers": [{"uri": "scene.bin"}]}')
        zf.writestr("scene.bin", "binary-mesh-data")
        zf.writestr("model.obj", "mtllib model.mtl")
        zf.writestr("model.mtl", "newmtl Default")
        zf.writestr("license.txt", "CC-BY 4.0")

    extracted = safe_extract_zip(gltf_zip, tmp_path / "gltf-out")

    assert set(extracted) == {"scene.gltf", "scene.bin", "model.obj", "model.mtl"}
    assert not (tmp_path / "gltf-out" / "license.txt").exists()


def test_unitypackage_preflight_rejects_scripts_and_collisions(tmp_path: Path) -> None:
    assets = tmp_path / "Project" / "Assets"
    assets.mkdir(parents=True)
    package = tmp_path / "unsafe.unitypackage"
    with tarfile.open(package, "w:gz") as archive:
        payload = b"Assets/Editor/Evil.cs"
        info = tarfile.TarInfo("abcdef/pathname")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(AssetSecurityError, match="Unsupported or unsafe"):
        validate_unitypackage_contents(package, assets)


def test_vector3_requires_three_finite_values() -> None:
    adapter = TypeAdapter(Vector3)
    assert adapter.validate_python([1, 2, 3]) == [1.0, 2.0, 3.0]
    with pytest.raises(ValidationError):
        adapter.validate_python([1, 2])
    with pytest.raises(ValidationError):
        adapter.validate_python([1, float("inf"), 3])


@pytest.mark.anyio
async def test_ssrf_rejects_non_https_and_private_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AssetSecurityError, match="HTTPS"):
        await validate_remote_url("http://example.com/model.glb")

    def private_lookup(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", private_lookup)
    with pytest.raises(AssetSecurityError, match="non-public"):
        await validate_remote_url("https://example.com/model.glb")


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
async def test_ambientcg_resolve_download_url_uses_model_naming_for_3d_prefixed_ids() -> None:
    """Regression test: ambientCG's download filenames differ by asset type - materials use
    "<id>_1K-PNG.zip" but 3D models add a quality tier ("<id>_LQ-1K-PNG.zip"). Guessing the
    material pattern for a model 404s every time - verified live against real ambientCG assets.
    """
    provider = AmbientCGProvider()

    model_url, model_warns = await provider.resolve_download_url("ambientcg:3DApple002")
    assert model_url == "https://ambientcg.com/get?file=3DApple002_LQ-1K-PNG.zip"
    assert not model_warns

    material_url, material_warns = await provider.resolve_download_url("ambientcg:Bricks097")
    assert material_url == "https://ambientcg.com/get?file=Bricks097_1K-PNG.zip"
    assert not material_warns


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
async def test_download_and_import_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    res = await download_and_import_asset(
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
async def test_download_import_failure_is_not_reported_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_project = tmp_path / "UnityProject"
    fake_assets = fake_project / "Assets"
    fake_assets.mkdir(parents=True)

    async def mock_resolve_paths() -> tuple[Path, Path]:
        return fake_project, fake_assets

    async def mock_download(_url: str, target: Path, **_kwargs: Any) -> int:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"model")
        return 5

    async def failed_import(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"success": False, "error": "Unity import failed"}

    monkeypatch.setattr(operations, "resolve_unity_paths", mock_resolve_paths)
    monkeypatch.setattr(operations, "download_file_stream", mock_download)
    monkeypatch.setattr(operations.bridge, "execute_capability", failed_import)
    result = await download_and_import_asset(url="https://example.com/model.glb")
    assert result.success is False
    assert result.imported_objects == []
    assert not (fake_assets / "VisoraDownloads" / "model.glb").exists()


@pytest.mark.anyio
async def test_import_local_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    res = await import_local_asset(
        source_path=str(local_file),
        target_folder="Assets/Models",
    )

    assert res.success is True
    assert res.asset_path == "Assets/Models/local_prop.fbx"
    assert res.file_size_bytes == len(b"sample_fbx_content")
    assert (fake_assets / "Models" / "local_prop.fbx").exists()


@pytest.mark.anyio
async def test_import_local_asset_rejects_path_escape_and_unsafe_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_project = tmp_path / "UnityProject"
    fake_assets = fake_project / "Assets"
    fake_assets.mkdir(parents=True)
    script = tmp_path / "payload.cs"
    script.write_text("class Payload {}")

    async def mock_resolve_paths() -> tuple[Path, Path]:
        return fake_project, fake_assets

    monkeypatch.setattr(operations, "resolve_unity_paths", mock_resolve_paths)
    unsafe = await import_local_asset(str(script))
    assert unsafe.success is False
    assert "unsafe" in (unsafe.error or "")

    safe_file = tmp_path / "model.obj"
    safe_file.write_text("v 0 0 0")
    escaped = await import_local_asset(str(safe_file), target_folder="Assets/../../outside")
    assert escaped.success is False
    assert "inside the Unity Assets" in (escaped.error or "")
    assert not (tmp_path / "outside").exists()


@pytest.mark.anyio
async def test_import_local_asset_uses_unique_name_and_rolls_back_on_unity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "model.fbx"
    source.write_bytes(b"model")
    fake_project = tmp_path / "UnityProject"
    fake_assets = fake_project / "Assets"
    existing = fake_assets / "Imports" / "model.fbx"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"original")

    async def mock_resolve_paths() -> tuple[Path, Path]:
        return fake_project, fake_assets

    async def successful_import(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"success": True, "importedObjects": ["Assets/Imports/model-1.fbx"]}

    monkeypatch.setattr(operations, "resolve_unity_paths", mock_resolve_paths)
    monkeypatch.setattr(operations.bridge, "execute_capability", successful_import)
    renamed = await import_local_asset(str(source), target_folder="Assets/Imports")
    assert renamed.success is True
    assert renamed.asset_path == "Assets/Imports/model-1.fbx"
    assert existing.read_bytes() == b"original"
    assert any("Destination existed" in warning for warning in renamed.warnings)

    async def failing_import(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"success": False, "error": "AssetDatabase import failed"}

    monkeypatch.setattr(operations.bridge, "execute_capability", failing_import)
    failed = await import_local_asset(str(source), target_folder="Assets/Imports")
    assert failed.success is False
    assert failed.imported_objects == []
    assert not (fake_assets / "Imports" / "model-2.fbx").exists()


@pytest.mark.anyio
async def test_inspect_imported_asset(monkeypatch: pytest.MonkeyPatch) -> None:
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

    res = await inspect_imported_asset("Assets/Models/robot.glb")
    assert res.success is True
    assert res.asset_path == "Assets/Models/robot.glb"
    assert res.model_importer_info is not None
    assert res.model_importer_info.animation_type == "Humanoid"
    assert res.model_importer_info.clip_count == 3
    assert "Idle" in res.animation_clips
    assert res.submesh_count == 2


@pytest.mark.anyio
async def test_instantiate_scene_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_execute_cap(code: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "game_object_name": "Knight",
            "game_object_path": "Characters/Knight",
            "instance_id": 4242,
            "world_position": [1.0, 0.0, 2.5],
        }

    monkeypatch.setattr(operations.bridge, "execute_capability", mock_execute_cap)

    res = await instantiate_scene_asset(
        asset_path="Assets/Characters/Knight.prefab",
        position=[1.0, 0.0, 2.5],
    )
    assert res.success is True
    assert res.game_object_name == "Knight"
    assert res.game_object_path == "Characters/Knight"
    assert res.instance_id == 4242
    assert res.world_position == [1.0, 0.0, 2.5]


def test_helpers_unique_destination(tmp_path: Path) -> None:
    dest = tmp_path / "model.glb"
    first, col = helpers.unique_destination(dest)
    assert first == dest
    assert col is None

    dest.touch()
    second, col2 = helpers.unique_destination(dest)
    assert second == tmp_path / "model-1.glb"
    assert col2 == str(dest)

    second.touch()
    third, col3 = helpers.unique_destination(dest)
    assert third == tmp_path / "model-2.glb"
    assert col3 == str(dest)


def test_helpers_cleanup_imported_path(tmp_path: Path) -> None:
    f = tmp_path / "test.fbx"
    m = tmp_path / "test.fbx.meta"
    f.touch()
    m.touch()
    assert f.exists()
    assert m.exists()
    helpers.cleanup_imported_path(f)
    assert not f.exists()
    assert not m.exists()

    d = tmp_path / "test_dir"
    d.mkdir()
    (d / "sub.txt").touch()
    helpers.cleanup_imported_path(d)
    assert not d.exists()


def test_helpers_unity_file_path(tmp_path: Path) -> None:
    folder = tmp_path / "Assets" / "Sub"
    file_path = folder / "Model.glb"
    assert helpers.unity_file_path("Assets/Sub", file_path, folder) == "Assets/Sub/Model.glb"


def test_helpers_resolve_target_folder(tmp_path: Path) -> None:
    assets = tmp_path / "UnityProject" / "Assets"
    assets.mkdir(parents=True)

    dest, upath = helpers.resolve_target_folder(assets, "Models/Props")
    assert dest == assets / "Models" / "Props"
    assert upath == "Assets/Models/Props"

    dest2, upath2 = helpers.resolve_target_folder(assets, "Assets/Textures")
    assert dest2 == assets / "Textures"
    assert upath2 == "Assets/Textures"

    with pytest.raises(AssetSecurityError, match="must resolve inside"):
        helpers.resolve_target_folder(assets, "../Escape")


def test_helpers_resolve_cache_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "UnityProject"
    assets = project / "Assets"
    assets.mkdir(parents=True)

    class GoodSettings:
        asset_cache_dir = "Library/VisoraCache"

    monkeypatch.setattr("backend.tools.asset.helpers.get_settings", GoodSettings)
    cache = helpers.resolve_cache_root(project, assets)
    assert cache == (project / "Library" / "VisoraCache").resolve()
    assert cache.exists()

    class BadSettings:
        asset_cache_dir = "Assets/UnsafeCache"

    monkeypatch.setattr("backend.tools.asset.helpers.get_settings", BadSettings)
    with pytest.raises(AssetSecurityError, match="outside the Unity Assets directory"):
        helpers.resolve_cache_root(project, assets)
