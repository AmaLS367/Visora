from backend.app import mcp
from backend.schemas.preview_record import (
    AnimationPreviewListResult,
    AnimationPreviewRecordResult,
)
from backend.tools.animation.preview_store import (
    get_preview_record,
    list_preview_records,
)


@mcp.tool()
async def get_animation_preview_record(
    preview_id: str,
) -> AnimationPreviewRecordResult:
    """
    Retrieves the complete, reproducible metadata and artifact manifest for a specific animation preview run.

    Args:
        preview_id: Unique preview run identifier (e.g. prev_20260910_111800_ab12cd34).

    Returns:
        An AnimationPreviewRecordResult containing the loaded AnimationPreviewRecord, or an error if not found.
    """
    record = get_preview_record(preview_id)
    if record is None:
        return AnimationPreviewRecordResult(
            success=False,
            error=f"Animation preview record '{preview_id}' not found.",
        )
    return AnimationPreviewRecordResult(success=True, record=record)


@mcp.tool()
async def list_animation_preview_records(
    clip_path: str | None = None,
    target_object_path: str | None = None,
    limit: int = 10,
) -> AnimationPreviewListResult:
    """
    Lists stored animation preview records with key metadata, sorted by creation timestamp descending.

    Args:
        clip_path: Optional filter by AnimationClip asset path or substring.
        target_object_path: Optional filter by target GameObject hierarchy path or substring.
        limit: Maximum number of preview summaries to return (default 10).

    Returns:
        An AnimationPreviewListResult containing summaries of matching preview runs and total count.
    """
    summaries = list_preview_records(
        clip_path=clip_path,
        target_object_path=target_object_path,
        limit=limit,
    )
    return AnimationPreviewListResult(
        success=True,
        records=summaries,
        total_count=len(summaries),
    )


__all__ = [
    "get_animation_preview_record",
    "list_animation_preview_records",
]
