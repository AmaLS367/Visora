import asyncio
import logging
import time

from backend.app import mcp
from backend.bridge import BridgeError, UnityBridge
from backend.schemas.queue import QueueStatusResult

logger = logging.getLogger("backend.tools.bridge.queue")
bridge = UnityBridge()


@mcp.tool()
async def check_ticket_status(ticket_id: str) -> QueueStatusResult:
    """
    Performs a single non-blocking check of a task ticket's status in the Unity task queue.

    Args:
        ticket_id: The unique ID of the queued ticket to inspect.

    Returns:
        QueueStatusResult with immediate status, progress, and result/error if resolved.
    """
    try:
        status_data = await bridge.get_queue_status(ticket_id)
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
                error=None,
            )
        if status == "failed":
            return QueueStatusResult(
                success=False,
                ticket_id=ticket_id,
                status=status,
                progress=progress,
                result=None,
                error=error or "Task execution failed in Unity Editor",
            )
        if status == "cancelled":
            return QueueStatusResult(
                success=False,
                ticket_id=ticket_id,
                status=status,
                progress=progress,
                result=None,
                error="Task was cancelled",
            )

        return QueueStatusResult(
            success=True,
            ticket_id=ticket_id,
            status=status,
            progress=progress,
            result=result,
            error=None,
        )

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
            success=False,
            ticket_id=ticket_id,
            status="error",
            progress=0.0,
            result=None,
            error=str(e),
        )


@mcp.tool()
async def wait_for_ticket(
    ticket_id: str,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
) -> QueueStatusResult:
    """
    Asynchronously polls the Unity task queue for the status of a specific ticket until completion, failure, or timeout.

    Args:
        ticket_id: The unique ID of the queued ticket to monitor.
        timeout: Maximum duration in seconds to poll before timing out. Defaults to 30.0.
        poll_interval: Time in seconds to wait between poll attempts. Defaults to 1.0.

    Returns:
        A QueueStatusResult detailing the outcome of the queued execution, progress, and elapsed duration.
    """
    start_time = time.perf_counter()

    while True:
        elapsed = round(time.perf_counter() - start_time, 2)
        try:
            status_data = await bridge.get_queue_status(ticket_id)
            raw_status = str(status_data.get("status", "pending"))
            status = raw_status.lower()
            progress = float(status_data.get("progress", 0.0))
            result = status_data.get("result")
            error = status_data.get("error") or status_data.get("errorMessage")

            logger.info(f"Polling ticket {ticket_id}: status={status}, progress={progress}, elapsed={elapsed}s")

            if status == "completed":
                return QueueStatusResult(
                    success=True,
                    ticket_id=ticket_id,
                    status=status,
                    progress=progress,
                    result=result,
                    duration_seconds=elapsed,
                    error=None,
                )
            if status == "failed":
                return QueueStatusResult(
                    success=False,
                    ticket_id=ticket_id,
                    status=status,
                    progress=progress,
                    result=None,
                    duration_seconds=elapsed,
                    error=error or "Task execution failed in Unity Editor",
                )
            if status == "cancelled":
                return QueueStatusResult(
                    success=False,
                    ticket_id=ticket_id,
                    status=status,
                    progress=progress,
                    result=None,
                    duration_seconds=elapsed,
                    error="Task was cancelled in Unity Editor",
                )

        except Exception as e:
            logger.warning(f"Transient error while polling ticket {ticket_id}: {e}. Retrying...")

        if elapsed >= timeout:
            logger.error(f"Polling ticket {ticket_id} timed out after {elapsed:.2f} seconds")
            return QueueStatusResult(
                success=False,
                ticket_id=ticket_id,
                status="timeout",
                progress=0.0,
                result=None,
                duration_seconds=elapsed,
                error=f"Polling timed out after {timeout} seconds",
            )

        await asyncio.sleep(poll_interval)
