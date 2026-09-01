"""
Backward compatibility module for queue operations.
Delegates to backend.tools.bridge.
"""

from backend.tools.bridge.queue import check_ticket_status, wait_for_ticket

__all__ = ["check_ticket_status", "wait_for_ticket"]
