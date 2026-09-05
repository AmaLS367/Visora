from typing import cast

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import AnimationBackupInfo, ListAnimationBackupsResult, RestoreAnimationClipResult
from backend.tools.animation.common import _bridge_supports, _require_edit_mode

_UNSUPPORTED_ERROR = "animation_authoring requires the Visora Unity package installed in the Unity project."


@mcp.tool()
async def list_animation_backups(clip_path: str) -> ListAnimationBackupsResult:
    """Lists VisoraBackups/ snapshots for one clip, newest first."""
    try:
        if not await _bridge_supports("animation_authoring"):
            return ListAnimationBackupsResult(success=False, error=_UNSUPPORTED_ERROR, clip_path=clip_path)

        payload = await animation_pkg.bridge.list_backups_native(clip_path)

        backups = [
            AnimationBackupInfo(
                backup_id=str(b["backupId"]),
                clip_path=str(b["clipPath"]),
                created_at=str(b["createdAt"]),
                operation=str(b["operation"]),
                size_bytes=int(b["sizeBytes"]),
            )
            for b in payload.get("backups", [])
        ]
        return ListAnimationBackupsResult(
            success=bool(payload.get("success", False)),
            error=cast("str | None", payload.get("error")),
            clip_path=cast("str | None", payload.get("clipPath", clip_path)),
            backups=backups,
        )
    except Exception as e:
        animation_pkg.logger.error("Error during list_animation_backups for '%s': %s", clip_path, e)
        return ListAnimationBackupsResult(success=False, error=str(e), clip_path=clip_path)


@mcp.tool()
async def restore_animation_clip(
    clip_path: str, backup_id: str, operation_id: str | None = None
) -> RestoreAnimationClipResult:
    """
    Restores a clip from a VisoraBackups/ snapshot returned by list_animation_backups. The
    state discarded by this call is itself backed up first, so a restore can be undone too.
    """
    try:
        edit_mode_error = await _require_edit_mode()
        if edit_mode_error is not None:
            return RestoreAnimationClipResult(success=False, error=edit_mode_error, clip_path=clip_path)

        if not await _bridge_supports("animation_authoring"):
            return RestoreAnimationClipResult(success=False, error=_UNSUPPORTED_ERROR, clip_path=clip_path)

        payload = await animation_pkg.bridge.restore_clip_native(clip_path, backup_id, operation_id=operation_id)

        warnings_raw = payload.get("warnings", [])
        warnings = [str(w) for w in warnings_raw] if isinstance(warnings_raw, list) else []

        return RestoreAnimationClipResult(
            success=bool(payload.get("success", False)),
            error=cast("str | None", payload.get("error")),
            clip_path=cast("str | None", payload.get("clipPath", clip_path)),
            restored_from_backup_id=cast("str | None", payload.get("restoredFromBackupId")),
            pre_restore_backup_id=cast("str | None", payload.get("preRestoreBackupId")),
            warnings=warnings,
        )
    except Exception as e:
        animation_pkg.logger.error("Error during restore_animation_clip for '%s': %s", clip_path, e)
        return RestoreAnimationClipResult(success=False, error=str(e), clip_path=clip_path)


__all__ = ["list_animation_backups", "restore_animation_clip"]
