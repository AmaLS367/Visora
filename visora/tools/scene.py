from visora.schemas import PlayModeManagementResult, SafeTransactionResult
from visora.server import mcp


@mcp.tool()
async def safe_transaction(editor_code: str, auto_save: bool = True) -> SafeTransactionResult:
    """
    Executes editor scripting code in a safe transaction, saving the active scene first.

    Args:
        editor_code: The C# editor script string to compile and execute.
        auto_save: If True, saves the scene automatically before executing the transaction to prevent loss of state.

    Returns:
        A SafeTransactionResult detailing whether the scene was saved, transaction ID, and outcome description.
    """
    # Empty decorated stub - no implementation yet
    return SafeTransactionResult(success=True, message="Transaction dry run successful")


@mcp.tool()
async def playmode_management(play: bool) -> PlayModeManagementResult:
    """
    Manages the Unity Editor Play Mode state.

    Args:
        play: Set to True to start play mode, or False to stop and exit back to edit mode.

    Returns:
        A PlayModeManagementResult detailing the playmode state change outcome.
    """
    # Empty decorated stub - no implementation yet
    return PlayModeManagementResult(success=True, is_playing=play, previous_state=not play, message="State toggled")
