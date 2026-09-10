import asyncio
import logging
import time
from typing import Any

from backend.app import mcp
from backend.bridge import BridgeError, UnityBridge
from backend.schemas.queue import QueueStatusResult
from backend.tools.errors import bridge_error

logger = logging.getLogger("backend.tools.bridge.queue")
bridge = UnityBridge()


def _parse_queue_status_payload(
    ticket_id: str, status_data: dict[str, Any], duration_seconds: float | None = None
) -> QueueStatusResult:
    raw_status = str(status_data.get("status", "pending"))
    status = raw_status.lower()
    progress = float(status_data.get("progress", 0.0))
    result = status_data.get("result")
    error = status_data.get("error") or status_data.get("errorMessage")

    if status == "completed":
        return QueueStatusResult(
            success=True,
            ticket_id=ticket_id,
            status=status,
            progress=progress,
            result=result,
            duration_seconds=duration_seconds,
            error=None,
        )
    if status == "failed":
        return QueueStatusResult(
            success=False,
            ticket_id=ticket_id,
            status=status,
            progress=progress,
            result=None,
            duration_seconds=duration_seconds,
            error=error or "Task execution failed in Unity Editor",
        )
    if status == "cancelled":
        fallback_cancelled_msg = (
            "Task was cancelled in Unity Editor" if duration_seconds is not None else "Task was cancelled"
        )
        return QueueStatusResult(
            success=False,
            ticket_id=ticket_id,
            status=status,
            progress=progress,
            result=None,
            duration_seconds=duration_seconds,
            error=error or fallback_cancelled_msg,
        )

    return QueueStatusResult(
        success=True,
        ticket_id=ticket_id,
        status=status,
        progress=progress,
        result=result,
        duration_seconds=duration_seconds,
        error=None,
    )


@mcp.tool()
async def check_ticket_status(
    ticket_id: str,
    wait: bool = False,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 1.0,
) -> QueueStatusResult:
    """
    Checks the status of a task ticket in the Unity task queue, optionally polling until completion.

    Args:
        ticket_id: The unique ID of the queued ticket to inspect.
        wait: If True, asynchronously polls until the ticket completes, fails, is cancelled, or times out.
        timeout_seconds: Maximum duration in seconds to poll when wait=True. Defaults to 30.0.
        poll_interval_seconds: Time in seconds between poll attempts when wait=True. Defaults to 1.0.

    Returns:
        QueueStatusResult with status, progress, result/error, and duration_seconds when waiting.
    """
    if not wait:
        try:
            status_data = await bridge.get_queue_status(ticket_id)
            return _parse_queue_status_payload(ticket_id, status_data)
        except BridgeError as e:
            logger.error(f"Bridge error while checking ticket {ticket_id}: {e}")
            return QueueStatusResult(
                success=False,
                ticket_id=ticket_id,
                status="error",
                progress=0.0,
                result=None,
                error=f"Bridge communication error: {e}",
            )
        except Exception as e:
            logger.error(f"Unexpected error checking ticket {ticket_id}: {e}")
            return QueueStatusResult(
                **bridge_error(e),
                ticket_id=ticket_id,
                status="error",
                progress=0.0,
                result=None,
            )

    start_time = time.perf_counter()

    while True:
        elapsed = round(time.perf_counter() - start_time, 2)
        try:
            status_data = await bridge.get_queue_status(ticket_id)
            raw_status = str(status_data.get("status", "pending")).lower()
            logger.info(f"Polling ticket {ticket_id}: status={raw_status}, elapsed={elapsed}s")

            if raw_status in ("completed", "failed", "cancelled"):
                return _parse_queue_status_payload(ticket_id, status_data, duration_seconds=elapsed)
        except Exception as e:
            logger.warning(f"Transient error while polling ticket {ticket_id}: {e}. Retrying...")

        if elapsed >= timeout_seconds:
            logger.error(f"Polling ticket {ticket_id} timed out after {elapsed:.2f} seconds")
            return QueueStatusResult(
                success=False,
                ticket_id=ticket_id,
                status="timeout",
                progress=0.0,
                result=None,
                duration_seconds=elapsed,
                error=f"Polling timed out after {timeout_seconds} seconds",
            )

        await asyncio.sleep(poll_interval_seconds)


__all__ = ["check_ticket_status"]
