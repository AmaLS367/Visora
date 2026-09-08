from __future__ import annotations

from typing import Any

from backend.app import mcp
from backend.bridge.client import UnityBridge
from backend.schemas.transaction import (
    AnimationTransactionResult,
)


@mcp.tool()
async def edit_animation_transaction(
    operations: list[dict[str, Any]],
    transaction_id: str | None = None,
    description: str | None = None,
) -> AnimationTransactionResult:
    """
    Executes an atomic batch of animation clip modifications inside an Editor Undo group.

    Guarantees atomic all-or-nothing execution: before modifying any asset, creates pre-mutation
    backups in VisoraBackups/ for every referenced clip. If any operation in the batch fails,
    immediately rolls back all affected clips to their pristine backup state and reverts the
    Undo group.

    Supported operations in `operations`:
    - {"operation_type": "set_keyframe", "clip_path": str, "target_path": str, "type_name": str, "property_name": str, "time": float, "values": list[float], "tangent_mode": str}
    - {"operation_type": "move_keyframe", "clip_path": str, "target_path": str, "type_name": str, "property_name": str, "old_time": float, "new_time": float}
    - {"operation_type": "remove_keyframe", "clip_path": str, "target_path": str, "type_name": str, "property_name": str, "time": float}
    - {"operation_type": "set_keyframe_hold", "clip_path": str, "target_path": str, "type_name": str, "property_name": str, "start_time": float, "duration": float, "values": list[float] | None}
    - {"operation_type": "create_event", "clip_path": str, "time": float, "function_name": str, "string_parameter": str, "float_parameter": float, "int_parameter": int}
    - {"operation_type": "remove_event", "clip_path": str, "time": float, "function_name": str}
    - {"operation_type": "ensure_continuity", "clip_path": str}

    Args:
        operations: List of operation dictionaries to execute sequentially.
        transaction_id: Optional custom transaction identifier.
        description: Human-readable description for the Editor Undo history.

    Returns:
        An AnimationTransactionResult recording success, modified keyframes count, backup IDs,
        or rollback status with error reason.
    """
    # Normalize dictionary keys for C# JSON deserializer
    normalized_ops = []
    for op in operations:
        normalized_ops.append(
            {
                "operationType": op.get("operation_type") or op.get("operationType", ""),
                "clipPath": op.get("clip_path") or op.get("clipPath", ""),
                "targetPath": op.get("target_path") or op.get("targetPath", ""),
                "typeName": op.get("type_name") or op.get("typeName", "Transform"),
                "propertyName": op.get("property_name") or op.get("propertyName", ""),
                "time": float(op.get("time", 0.0)),
                "oldTime": float(op.get("old_time") or op.get("oldTime", 0.0)),
                "newTime": float(op.get("new_time") or op.get("newTime", 0.0)),
                "startTime": float(op.get("start_time") or op.get("startTime", 0.0)),
                "duration": float(op.get("duration", 0.0)),
                "value": float(op.get("value", 0.0)),
                "values": [float(v) for v in op["values"]] if op.get("values") is not None else None,
                "tangentMode": op.get("tangent_mode") or op.get("tangentMode", "smooth"),
                "functionName": op.get("function_name") or op.get("functionName", ""),
                "intParameter": int(op.get("int_parameter") or op.get("intParameter", 0)),
                "floatParameter": float(op.get("float_parameter") or op.get("floatParameter", 0.0)),
                "stringParameter": op.get("string_parameter") or op.get("stringParameter", ""),
            }
        )

    async with UnityBridge() as bridge:
        resp = await bridge.execute_animation_transaction_native(
            operations=normalized_ops,
            transaction_id=transaction_id,
            description=description,
        )

    return AnimationTransactionResult(
        success=bool(resp.get("success", False)),
        error=resp.get("error"),
        transaction_id=str(resp.get("transactionId", transaction_id or "")),
        applied_operations_count=int(resp.get("appliedOperationsCount", 0)),
        keyframes_modified_count=int(resp.get("keyframesModifiedCount", 0)),
        rollback_performed=bool(resp.get("rollbackPerformed", False)),
        backup_ids=list(resp.get("backupIds", [])),
        affected_clips=list(resp.get("affectedClips", [])),
        warnings=list(resp.get("warnings", [])),
    )
