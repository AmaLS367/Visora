import pytest

import backend.tools.animation as animation_pkg
from backend.tools.animation.backups import list_animation_backups, restore_animation_clip


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeBridge:
    def __init__(self, *, is_playing: bool = False, native_supported: bool = True) -> None:
        self.calls: list[str] = []
        self._is_playing = is_playing
        self._native_supported = native_supported

    async def supports_feature(self, feature: str) -> bool:
        return self._native_supported and feature == "animation_authoring"

    async def get_editor_state(self) -> dict[str, object]:
        return {"isPlaying": self._is_playing}

    async def list_backups_native(self, clip_path: str) -> dict[str, object]:
        self.calls.append("list_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "backups": [
                {
                    "backupId": "Assets__A.anim/20260905-090000-set_animation_keyframe.anim",
                    "clipPath": clip_path,
                    "createdAt": "2026-09-05T09:00:00Z",
                    "operation": "set_animation_keyframe",
                    "sizeBytes": 512,
                }
            ],
        }

    async def restore_clip_native(
        self, clip_path: str, backup_id: str, operation_id: str | None = None
    ) -> dict[str, object]:
        del operation_id
        self.calls.append("restore_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "restoredFromBackupId": backup_id,
            "preRestoreBackupId": "Assets__A.anim/20260905-091500-restore_animation_clip.anim",
            "warnings": [],
        }


@pytest.mark.anyio
async def test_list_animation_backups_parses_native_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await list_animation_backups(clip_path="Assets/A.anim")

    assert fake.calls == ["list_native"]
    assert result.success is True
    assert len(result.backups) == 1
    assert result.backups[0].operation == "set_animation_keyframe"


@pytest.mark.anyio
async def test_restore_animation_clip_reports_pre_restore_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await restore_animation_clip(
        clip_path="Assets/A.anim", backup_id="Assets__A.anim/20260905-090000-set_animation_keyframe.anim"
    )

    assert fake.calls == ["restore_native"]
    assert result.success is True
    assert result.pre_restore_backup_id is not None


@pytest.mark.anyio
async def test_restore_animation_clip_passes_operation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()
    captured_kwargs: dict[str, object] = {}

    async def capturing_restore_clip_native(
        clip_path: str, backup_id: str, operation_id: str | None = None
    ) -> dict[str, object]:
        captured_kwargs["operation_id"] = operation_id
        return await _FakeBridge.restore_clip_native(fake, clip_path, backup_id, operation_id=operation_id)

    fake.restore_clip_native = capturing_restore_clip_native  # type: ignore[method-assign]
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await restore_animation_clip(
        clip_path="Assets/A.anim",
        backup_id="Assets__A.anim/20260905-090000-set_animation_keyframe.anim",
        operation_id="backup-op-99",
    )

    assert result.success is True
    assert captured_kwargs["operation_id"] == "backup-op-99"


@pytest.mark.anyio
async def test_restore_animation_clip_refuses_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await restore_animation_clip(clip_path="Assets/A.anim", backup_id="b1")

    assert result.success is False
    assert result.error is not None
    assert "Edit Mode" in result.error
    assert fake.calls == []


@pytest.mark.anyio
async def test_backup_tools_unsupported_when_package_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge(native_supported=False)
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    list_res = await list_animation_backups(clip_path="Assets/A.anim")
    assert list_res.success is False
    assert "requires the Visora Unity package" in (list_res.error or "")

    restore_res = await restore_animation_clip(clip_path="Assets/A.anim", backup_id="b1")
    assert restore_res.success is False
    assert "requires the Visora Unity package" in (restore_res.error or "")
    assert fake.calls == []
