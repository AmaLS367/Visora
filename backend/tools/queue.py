import asyncio
import logging
import time

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import QueueStatusResult

logger = logging.getLogger("backend.tools.queue")

# Instantiate unity bridge for queue operations
bridge = UnityBridge()


@mcp.tool()
async def wait_for_ticket(
    ticket_id: str,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
) -> QueueStatusResult:
    """
    Asynchronously polls the Unity task queue for the status of a specific ticket until completion or timeout.

    Args:
        ticket_id: The unique ID of the queued ticket to monitor.
        timeout: Maximum duration in seconds to poll before timing out. Defaults to 30.0.
        poll_interval: Time in seconds to wait between poll attempts. Defaults to 1.0.

    Returns:
        A QueueStatusResult detailing the outcome of the queued execution, or timeout state.
    """
    start_time = time.time()

    while True:
        try:
            # Poll status of the ticket from the Unity Editor bridge
            status_data = await bridge.get_queue_status(ticket_id)
            raw_status = str(status_data.get("status", "pending"))
            status = raw_status.lower()
            progress = status_data.get("progress", 0.0)
            result = status_data.get("result")
            error = status_data.get("error") or status_data.get("errorMessage")

            logger.info(f"Polling ticket {ticket_id}: status={status}, progress={progress}")

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

        except Exception as e:
            logger.warning(f"Error while polling ticket {ticket_id}: {e}. Retrying...")
            # We don't abort on request failures; we continue trying until timeout
            pass

        # Check if we have timed out
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            logger.error(f"Polling ticket {ticket_id} timed out after {elapsed:.2f} seconds")
            return QueueStatusResult(
                success=False,
                ticket_id=ticket_id,
                status="timeout",
                progress=0.0,
                result=None,
                error=f"Polling timed out after {timeout} seconds",
            )

        await asyncio.sleep(poll_interval)
