import base64
import io
import json
import math
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, UnidentifiedImageError

from backend.schemas import FrameMotionMetrics, VisualCapture, VisualComparisonResult


def _save_image_artifact(
    image: str | bytes | Image.Image,
    prefix: str = "screenshot",
    subfolder: str = "screenshots",
) -> Path:
    """
    Saves an image (from base64 string, raw bytes, or PIL Image) as a PNG artifact on disk.

    Returns:
        The absolute Path to the saved image file.
    """
    artifacts_dir = Path("artifacts") / subfolder
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    file_path = (artifacts_dir / f"{prefix}_{uuid.uuid4().hex[:8]}.png").resolve()

    if isinstance(image, str):
        raw_bytes = base64.b64decode(image, validate=False)
        file_path.write_bytes(raw_bytes)
    elif isinstance(image, bytes):
        file_path.write_bytes(image)
    elif isinstance(image, Image.Image):
        image.save(file_path, format="PNG")
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    return file_path


def _create_side_by_side_comparison(
    left_image: Image.Image,
    right_image: Image.Image,
    left_label: str = "Game Camera",
    right_label: str = "Diagnostic Lit",
) -> Image.Image:
    """Stitches two images horizontally with clear label headers into a single comparison image."""
    w = max(left_image.width, right_image.width)
    h = max(left_image.height, right_image.height)
    img1 = left_image.resize((w, h)) if left_image.size != (w, h) else left_image
    img2 = right_image.resize((w, h)) if right_image.size != (w, h) else right_image

    header_h = 28
    pad = 8
    total_w = w * 2 + pad * 3
    total_h = h + header_h + pad * 2

    canvas = Image.new("RGB", (total_w, total_h), color=(28, 28, 32))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad + 4, pad + 4), left_label, fill=(230, 230, 230))
    draw.text((pad * 2 + w + 4, pad + 4), right_label, fill=(230, 230, 230))

    canvas.paste(img1, (pad, pad + header_h))
    canvas.paste(img2, (pad * 2 + w, pad + header_h))
    return canvas


def _create_contact_sheet(
    images: list[Image.Image],
    labels: list[str],
    cols: int = 3,
) -> Image.Image:
    """Assembles a list of images into a labelled grid contact sheet."""
    if not images:
        raise ValueError("Cannot create contact sheet from empty image list")
    n = len(images)
    cols = max(1, min(cols, n))
    rows = math.ceil(n / cols)
    w, h = images[0].width, images[0].height
    pad = 8
    header_h = 24
    cell_w = w
    cell_h = h + header_h
    total_w = cols * cell_w + (cols + 1) * pad
    total_h = rows * cell_h + (rows + 1) * pad
    sheet = Image.new("RGB", (total_w, total_h), color=(25, 25, 28))
    draw = ImageDraw.Draw(sheet)
    for idx, (img, label) in enumerate(zip(images, labels, strict=False)):
        r = idx // cols
        c = idx % cols
        x = pad + c * (cell_w + pad)
        y = pad + r * (cell_h + pad)
        draw.text((x + 4, y + 4), label, fill=(220, 220, 220))
        resized = img.resize((w, h)) if img.size != (w, h) else img
        sheet.paste(resized, (x, y + header_h))
    return sheet


def _load_image(source: str | Path | Image.Image) -> Image.Image:
    """Loads a PIL RGB Image from a PIL Image, local file path, or base64 string."""
    if isinstance(source, Image.Image):
        return source.convert("RGB")
    if isinstance(source, Path) or (isinstance(source, str) and Path(source).is_file()):
        return Image.open(source).convert("RGB")
    if isinstance(source, str):
        return _decode_image(source)
    raise ValueError(f"Cannot load image from {type(source)}")


def _extract_result_payload(response: dict[str, Any]) -> dict[str, Any]:
    """
    Extracts and validates the result payload from a Unity bridge response dictionary.

    Args:
        response: Raw response dictionary returned by the Unity HTTP bridge.

    Returns:
        The extracted inner payload as a dictionary.

    Raises:
        RuntimeError: If the response indicates failure, contains errors, or has an invalid structure.
    """
    error = response.get("error") or response.get("errorMessage")
    if error:
        raise RuntimeError(str(error))
    if response.get("success") is False:
        raise RuntimeError("Unity bridge reported an unsuccessful execution")

    payload = response.get("result", response)
    if isinstance(payload, str):
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise RuntimeError("Unity execution returned a non-object JSON payload")
        payload = parsed
    if not isinstance(payload, dict):
        raise RuntimeError("Unity execution returned an unsupported payload")
    return payload


def _decode_image(image_base64: str) -> Image.Image:
    """
    Decodes a base64-encoded image string into an RGB PIL Image instance.

    Args:
        image_base64: Base64 string representing PNG or JPEG bytes.

    Returns:
        A PIL.Image.Image in RGB mode.

    Raises:
        ValueError: If the base64 data is corrupt or cannot be decoded as a valid image.
    """
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
        image = Image.open(io.BytesIO(image_bytes))
        return image.convert("RGB")
    except (ValueError, UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid base64 image data") from exc


def _normalize_threshold(threshold: int) -> int:
    """Clamps a pixel delta threshold to the valid 8-bit channel range [0, 255]."""
    return max(0, min(255, threshold))


def _validate_video_request(
    duration_seconds: float,
    fps: int,
    width: int,
    height: int,
    max_fps: int,
) -> str | None:
    """
    Validates capture video request parameters against safety and resource bounds.

    Returns:
        An error message string if any parameter is invalid, or None if the request is valid.
    """
    if duration_seconds < 0.1 or duration_seconds > 10.0:
        return "duration_seconds must be between 0.1 and 10.0"
    if fps < 1 or fps > max_fps:
        return f"fps must be between 1 and {max_fps}"
    if width <= 0 or height <= 0:
        return "width and height must be positive integers"
    if width > 1920 or height > 1080:
        return "width and height must not exceed 1920x1080"
    if math.ceil(duration_seconds * fps) > 120:
        return "video capture must not exceed 120 sampled frames"
    return None


def _payload_warnings(payload: dict[str, Any]) -> list[str]:
    """Safely extracts a list of warning strings from a Unity bridge response payload."""
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        return [str(warnings)]
    return [str(warning) for warning in warnings]


def _payload_float(value: Any, default: float = 0.0) -> float:
    """Coerces a potentially nullable or loosely typed response value into a float."""
    if value is None:
        return default
    return float(value)


def _frame_count(duration_seconds: float, fps: int) -> int:
    """Calculates the total number of frames to sample for a given duration and frame rate."""
    return max(1, math.ceil(duration_seconds * fps))


def _encode_frames_to_mp4(
    frame_images: Sequence[str | Path], fps: float, width: int, height: int
) -> tuple[bytes, Path]:
    """
    Encodes a list of image frames (file paths or base64 strings) into an H.264 MP4 video file saved in artifacts/.

    Args:
        frame_images: Ordered list of frame file paths or base64-encoded frame images.
        fps: Frames per second to encode at - the rate the capture actually achieved, not the requested one.
        width: Frame width in pixels.
        height: Frame height in pixels.

    Returns:
        A tuple of (mp4_bytes, absolute_file_path).
    """
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / f"visora-video-{uuid.uuid4().hex}.mp4"

    with cast(Any, imageio.get_writer(output_path, fps=fps, codec="libx264", macro_block_size=None)) as writer:
        for frame_src in frame_images:
            image = _load_image(frame_src).resize((width, height))
            writer.append_data(np.asarray(image))

    return output_path.read_bytes(), output_path.resolve()


def _capture_from_payload(mode: str, payload: dict[str, Any], fallback_camera_name: str) -> tuple[VisualCapture, Path]:
    """
    Constructs a VisualCapture model instance from a raw Unity capture payload, saving the PNG artifact to disk.

    Args:
        mode: Visual inspection mode ('game_camera' or 'diagnostic_lit').
        payload: Response dictionary containing imageBase64, dimensions, and optional warnings.
        fallback_camera_name: Default camera name to assign if not present in the payload.

    Returns:
        A tuple of (VisualCapture, Path).
    """
    image_base64 = payload.get("imageBase64") or payload.get("image_base64")
    if not isinstance(image_base64, str) or not image_base64:
        raise RuntimeError("Unity visual capture response did not include imageBase64")

    saved_path = _save_image_artifact(image_base64, prefix=mode, subfolder="screenshots")

    capture = VisualCapture(
        mode=mode,
        file_path=str(saved_path),
        width=int(payload["width"]),
        height=int(payload["height"]),
        camera_name=str(payload.get("cameraName", fallback_camera_name)),
        warnings=_payload_warnings(payload),
    )
    return capture, saved_path


def compare_images_data(
    before_image: str | Path | Image.Image,
    after_image: str | Path | Image.Image,
    threshold: int = 8,
) -> tuple[VisualComparisonResult, Path | None]:
    """
    Compares two images pixel-by-pixel, computes visual difference metrics, and saves a difference visualization artifact.

    Args:
        before_image: Base64 string, Path, or PIL Image of reference.
        after_image: Base64 string, Path, or PIL Image of target.
        threshold: Per-channel color delta threshold required to register a pixel change.

    Returns:
        A tuple of (VisualComparisonResult, diff_image_path).
    """
    try:
        before = _load_image(before_image)
        after = _load_image(after_image)
    except (ValueError, OSError) as exc:
        return VisualComparisonResult(success=False, error=str(exc)), None

    if before.size != after.size:
        return (
            VisualComparisonResult(
                success=False,
                error="screenshots must have matching dimensions",
                same_dimensions=False,
            ),
            None,
        )

    norm_threshold = _normalize_threshold(threshold)
    width, height = before.size
    total_pixels = width * height

    arr_before = np.asarray(before, dtype=np.int16)
    arr_after = np.asarray(after, dtype=np.int16)

    diff = np.abs(arr_before - arr_after)
    pixel_max_delta = np.max(diff, axis=-1)
    max_delta = int(np.max(pixel_max_delta)) if total_pixels else 0
    delta_sum = int(np.sum(diff)) if total_pixels else 0

    changed_mask = pixel_max_delta > norm_threshold
    changed_pixels = int(np.count_nonzero(changed_mask))

    diff_path: Path | None = None
    if changed_pixels:
        ys, xs = np.where(changed_mask)
        changed_bounds = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]

        # Generate difference overlay visualization
        overlay = np.asarray(after, dtype=np.uint8).copy()
        overlay[changed_mask] = [255, 60, 60]
        diff_img = Image.fromarray(overlay)
        diff_path = _save_image_artifact(diff_img, prefix="diff", subfolder="comparisons")
    else:
        changed_bounds = None

    result = VisualComparisonResult(
        success=True,
        same_dimensions=True,
        width=width,
        height=height,
        changed_pixel_ratio=changed_pixels / total_pixels if total_pixels else 0.0,
        mean_delta=delta_sum / (total_pixels * 3) if total_pixels else 0.0,
        max_delta=max_delta,
        changed_bounds=changed_bounds,
        diff_image_path=str(diff_path) if diff_path else None,
    )
    return result, diff_path


def _motion_metric_from_frames(
    from_frame: int, to_frame: int, before_source: str, after_source: str
) -> FrameMotionMetrics:
    """
    Computes inter-frame motion metrics (pixel difference ratio, delta, changed bounds) between two frames.
    """
    comparison, _ = compare_images_data(before_source, after_source)
    return FrameMotionMetrics(
        from_frame=from_frame,
        to_frame=to_frame,
        changed_pixel_ratio=comparison.changed_pixel_ratio,
        mean_delta=comparison.mean_delta,
        max_delta=comparison.max_delta,
        changed_bounds=comparison.changed_bounds,
    )
