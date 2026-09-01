import base64
import io
import json
import math
import uuid
from pathlib import Path
from typing import Any, cast

import imageio.v2 as imageio
import numpy as np
from PIL import Image, UnidentifiedImageError

from backend.schemas import FrameMotionMetrics, VisualCapture, VisualComparisonResult


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


def _encode_frames_to_mp4(frame_images_base64: list[str], fps: int, width: int, height: int) -> tuple[bytes, Path]:
    """
    Encodes a list of base64 image frames into an H.264 MP4 video file saved in artifacts/.

    Args:
        frame_images_base64: Ordered list of base64-encoded frame images.
        fps: Target frames per second.
        width: Frame width in pixels.
        height: Frame height in pixels.

    Returns:
        A tuple of (mp4_bytes, absolute_file_path).
    """
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / f"visora-video-{uuid.uuid4().hex}.mp4"

    with cast(Any, imageio.get_writer(output_path, fps=fps, codec="libx264", macro_block_size=None)) as writer:
        for image_base64 in frame_images_base64:
            image = _decode_image(image_base64).resize((width, height))
            writer.append_data(np.asarray(image))

    return output_path.read_bytes(), output_path.resolve()


def _capture_from_payload(mode: str, payload: dict[str, Any], fallback_camera_name: str) -> VisualCapture:
    """
    Constructs a VisualCapture model instance from a raw Unity capture payload.

    Args:
        mode: Visual inspection mode ('game_camera' or 'diagnostic_lit').
        payload: Response dictionary containing imageBase64, dimensions, and optional warnings.
        fallback_camera_name: Default camera name to assign if not present in the payload.

    Returns:
        A validated VisualCapture schema object.
    """
    image_base64 = payload.get("imageBase64") or payload.get("image_base64")
    if not isinstance(image_base64, str) or not image_base64:
        raise RuntimeError("Unity visual capture response did not include imageBase64")
    return VisualCapture(
        mode=mode,
        image_base64=image_base64,
        width=int(payload["width"]),
        height=int(payload["height"]),
        camera_name=str(payload.get("cameraName", fallback_camera_name)),
        warnings=_payload_warnings(payload),
    )


def compare_images_data(
    before_image_base64: str,
    after_image_base64: str,
    threshold: int = 8,
) -> VisualComparisonResult:
    """
    Compares two base64-encoded images pixel-by-pixel to compute visual difference metrics and changed bounding box.

    Args:
        before_image_base64: Base64 string of the reference image.
        after_image_base64: Base64 string of the target image.
        threshold: Per-channel color delta threshold required to register a pixel change.

    Returns:
        A VisualComparisonResult with changed pixel ratio, mean delta, max delta, and bounding box coordinates.
    """
    try:
        before = _decode_image(before_image_base64)
        after = _decode_image(after_image_base64)
    except ValueError as exc:
        return VisualComparisonResult(success=False, error=str(exc))

    if before.size != after.size:
        return VisualComparisonResult(
            success=False,
            error="screenshots must have matching dimensions",
            same_dimensions=False,
        )

    norm_threshold = _normalize_threshold(threshold)
    width, height = before.size
    total_pixels = width * height
    changed_pixels = 0
    delta_sum = 0
    max_delta = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    before_pixels = list(before.get_flattened_data())
    after_pixels = list(after.get_flattened_data())
    for index, (before_pixel_raw, after_pixel_raw) in enumerate(zip(before_pixels, after_pixels, strict=True)):
        before_pixel = cast(tuple[int, int, int], before_pixel_raw)
        after_pixel = cast(tuple[int, int, int], after_pixel_raw)
        x = index % width
        y = index // width
        deltas = [abs(before_pixel[channel] - after_pixel[channel]) for channel in range(3)]
        pixel_max_delta = max(deltas)
        max_delta = max(max_delta, pixel_max_delta)
        delta_sum += sum(deltas)
        if pixel_max_delta > norm_threshold:
            changed_pixels += 1
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    changed_bounds = [min_x, min_y, max_x, max_y] if changed_pixels else None
    return VisualComparisonResult(
        success=True,
        same_dimensions=True,
        width=width,
        height=height,
        changed_pixel_ratio=changed_pixels / total_pixels if total_pixels else 0.0,
        mean_delta=delta_sum / (total_pixels * 3) if total_pixels else 0.0,
        max_delta=max_delta,
        changed_bounds=changed_bounds,
    )


def _motion_metric_from_frames(
    from_frame: int, to_frame: int, before_base64: str, after_base64: str
) -> FrameMotionMetrics:
    """
    Computes inter-frame motion metrics (pixel difference ratio, delta, changed bounds) between two frames.
    """
    comparison = compare_images_data(before_base64, after_base64)
    return FrameMotionMetrics(
        from_frame=from_frame,
        to_frame=to_frame,
        changed_pixel_ratio=comparison.changed_pixel_ratio,
        mean_delta=comparison.mean_delta,
        max_delta=comparison.max_delta,
        changed_bounds=comparison.changed_bounds,
    )
