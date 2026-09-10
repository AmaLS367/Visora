import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.schemas.preview_record import (
    AnimationPreviewRecord,
    AnimationPreviewRecordSummary,
)

logger = logging.getLogger(__name__)

DEFAULT_PREVIEWS_SUBDIR = Path("artifacts") / "animation_previews"


def generate_preview_id() -> str:
    """
    Generates a unique, collision-proof, lexicographically sortable preview identifier.
    Format: prev_YYYYMMDD_HHMMSS_<8-char-hex>
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    unique_suffix = uuid.uuid4().hex[:8]
    return f"prev_{timestamp}_{unique_suffix}"


def get_previews_root_dir(base_dir: Path | None = None) -> Path:
    """Returns the root directory where preview runs are organized."""
    root = (base_dir or Path()) / DEFAULT_PREVIEWS_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def get_preview_dir(preview_id: str, base_dir: Path | None = None) -> Path:
    """
    Returns and ensures the isolated directory for a specific preview run.
    Format: artifacts/animation_previews/<preview_id>/
    """
    preview_dir = get_previews_root_dir(base_dir) / preview_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    return preview_dir.resolve()


def record_to_summary(record: AnimationPreviewRecord) -> AnimationPreviewRecordSummary:
    """Extracts a lightweight summary from a full preview record."""
    duration = record.capture_settings.requested_end_time - record.capture_settings.requested_start_time
    is_static = record.motion_summary.is_static if record.motion_summary else False
    return AnimationPreviewRecordSummary(
        preview_id=record.preview_id,
        created_at=record.created_at,
        target_object_path=record.target_object_path,
        clip_path=record.clip.clip_path,
        clip_name=record.clip.clip_name,
        camera_name=record.camera.rendered_camera_name,
        frame_count=record.capture_settings.frame_count,
        duration=max(0.0, round(duration, 3)),
        is_static=is_static,
        mp4_path=record.artifacts.mp4_path,
        record_path=record.artifacts.record_path,
    )


def save_preview_record(
    record: AnimationPreviewRecord,
    base_dir: Path | None = None,
) -> Path:
    """
    Atomically persists an AnimationPreviewRecord as record.json in its preview directory.
    Uses temporary file + atomic rename to guarantee zero partial/corrupted records.

    Returns:
        Absolute Path to the saved record.json.
    """
    preview_dir = get_preview_dir(record.preview_id, base_dir)
    target_file = preview_dir / "record.json"
    temp_file = preview_dir / f"record.json.tmp_{uuid.uuid4().hex[:8]}"

    # Update record_path in the record if necessary
    record.artifacts.record_path = str(target_file.resolve())

    payload = record.model_dump_json(indent=2)
    temp_file.write_text(payload, encoding="utf-8")
    temp_file.replace(target_file)

    logger.debug("Saved preview record %s to %s", record.preview_id, target_file)
    return target_file.resolve()


def get_preview_record(
    preview_id: str,
    base_dir: Path | None = None,
) -> AnimationPreviewRecord | None:
    """
    Loads and validates an AnimationPreviewRecord by its ID.
    Returns None if the record does not exist or cannot be deserialized.
    """
    preview_dir = get_previews_root_dir(base_dir) / preview_id
    record_file = preview_dir / "record.json"
    if not record_file.is_file():
        logger.debug("Preview record file not found: %s", record_file)
        return None

    try:
        content = record_file.read_text(encoding="utf-8")
        return AnimationPreviewRecord.model_validate_json(content)
    except Exception as exc:
        logger.warning("Failed to load preview record from %s: %exc", record_file, exc)
        return None


def list_preview_records(
    clip_path: str | None = None,
    target_object_path: str | None = None,
    limit: int = 10,
    base_dir: Path | None = None,
) -> list[AnimationPreviewRecordSummary]:
    """
    Scans stored preview records, filters them, and returns summaries sorted by created_at descending.
    """
    root_dir = get_previews_root_dir(base_dir)
    if not root_dir.is_dir():
        return []

    summaries: list[AnimationPreviewRecordSummary] = []
    for entry in root_dir.iterdir():
        if not entry.is_dir():
            continue
        record_file = entry / "record.json"
        if not record_file.is_file():
            continue

        try:
            content = record_file.read_text(encoding="utf-8")
            data = json.loads(content)
            # Lightweight check before full validation
            rec_clip_path = data.get("clip", {}).get("clip_path", "")
            rec_target = data.get("target_object_path", "")

            if clip_path and clip_path.lower() not in rec_clip_path.lower():
                continue
            if target_object_path and target_object_path.lower() not in rec_target.lower():
                continue

            record = AnimationPreviewRecord.model_validate(data)
            summaries.append(record_to_summary(record))
        except Exception as exc:
            logger.debug("Skipping unparseable record at %s: %s", record_file, exc)
            continue

    # Sort descending by created_at
    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries[: max(1, limit)]


def prune_preview_records(
    max_count: int = 50,
    base_dir: Path | None = None,
) -> int:
    """
    Removes the oldest preview directories if total count exceeds max_count.
    Returns number of pruned directories.
    """
    root_dir = get_previews_root_dir(base_dir)
    if not root_dir.is_dir() or max_count <= 0:
        return 0

    all_dirs: list[tuple[float, Path]] = []
    for entry in root_dir.iterdir():
        if entry.is_dir():
            try:
                all_dirs.append((entry.stat().st_mtime, entry))
            except OSError:
                continue

    if len(all_dirs) <= max_count:
        return 0

    # Sort ascending by mtime (oldest first)
    all_dirs.sort(key=lambda item: item[0])
    to_remove = all_dirs[: len(all_dirs) - max_count]

    pruned = 0
    for _, path in to_remove:
        try:
            shutil.rmtree(path)
            pruned += 1
        except Exception as exc:
            logger.warning("Failed to remove old preview directory %s: %s", path, exc)

    return pruned
