from typing import Any

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas.transaction import AnimationTransactionResult
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, logger, warns

_CAPABILITY = "animation_transactions"

_VALID_TANGENT_MODES = {"smooth", "linear", "step", "ease_in", "ease_out", "ease_in_out"}

# Op types for which a tangent mode is meaningful; it is dropped from every other op.
_TANGENT_OP_TYPES = {"set_keyframe", "set_keyframe_hold"}


def _fail(message: str, transaction_id: str | None) -> AnimationTransactionResult:
    return AnimationTransactionResult(
        success=False,
        error=message,
        transaction_id=transaction_id or "",
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

    `tangent_mode` must be one of: smooth, linear, step, ease_in, ease_out, ease_in_out.
    For set_keyframe / set_keyframe_hold, pass either `values` (per-channel) or `value` (single);
    an explicit `value` of 0.0 is honoured.

    Args:
        operations: List of operation dictionaries to execute sequentially.
        transaction_id: Optional custom transaction identifier.
        description: Human-readable description for the Editor Undo history.

    Returns:
        An AnimationTransactionResult recording success, modified keyframes count, backup IDs,
        or rollback status with error reason.
    """
    normalized_ops: list[dict[str, Any]] = []
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            return _fail(f"operations[{index}] must be an object.", transaction_id)

        op_type = str(op.get("operation_type") or op.get("operationType") or "")

        tangent_mode = op.get("tangent_mode") or op.get("tangentMode") or "smooth"
        if op_type in _TANGENT_OP_TYPES and tangent_mode not in _VALID_TANGENT_MODES:
            return _fail(
                f"operations[{index}] tangent_mode '{tangent_mode}' is not one of: "
                f"{', '.join(sorted(_VALID_TANGENT_MODES))}.",
                transaction_id,
            )

        has_value = "value" in op or "values" in op
        raw_values = op.get("values")
        if raw_values is not None:
            values: list[float] | None = [float(v) for v in raw_values]
        elif "value" in op:
            values = [float(op["value"])]
        else:
            values = None

        normalized_ops.append(
            {
                "operationType": op_type,
                "clipPath": op.get("clip_path") or op.get("clipPath") or "",
                "targetPath": op.get("target_path") or op.get("targetPath") or "",
                "typeName": op.get("type_name") or op.get("typeName") or "Transform",
                "propertyName": op.get("property_name") or op.get("propertyName") or "",
                "time": float(op.get("time", 0.0) or 0.0),
                "oldTime": float(op.get("old_time") or op.get("oldTime", 0.0)),
                "newTime": float(op.get("new_time") or op.get("newTime", 0.0)),
                "startTime": float(op.get("start_time") or op.get("startTime", 0.0)),
                "duration": float(op.get("duration", 0.0) or 0.0),
                "value": float(op.get("value", 0.0) or 0.0),
                "hasValue": has_value,
                "values": values,
                "tangentMode": tangent_mode if op_type in _TANGENT_OP_TYPES else "",
                "functionName": op.get("function_name") or op.get("functionName") or "",
                "intParameter": int(op.get("int_parameter") or op.get("intParameter", 0)),
                "floatParameter": float(op.get("float_parameter") or op.get("floatParameter", 0.0)),
                "stringParameter": op.get("string_parameter") or op.get("stringParameter") or "",
            }
        )

    edit_mode_err = await _require_edit_mode()
    if edit_mode_err:
        return _fail(edit_mode_err, transaction_id)

    if not await _bridge_supports(_CAPABILITY):
        return _fail(
            f"Unity bridge does not support capability '{_CAPABILITY}'. Update Visora Unity package.",
            transaction_id,
        )

    try:
        resp = await animation_pkg.bridge.execute_animation_transaction_native(
            operations=normalized_ops,
            transaction_id=transaction_id,
            description=description,
        )
    except Exception as exc:
        logger.exception("Error executing edit_animation_transaction")
        return _fail(f"Bridge call failed: {exc}", transaction_id)

    return AnimationTransactionResult(
        success=bool(resp.get("success", False)),
        error=resp.get("error"),
        transaction_id=str(resp.get("transactionId", transaction_id or "")),
        applied_operations_count=int(resp.get("appliedOperationsCount", 0)),
        keyframes_modified_count=int(resp.get("keyframesModifiedCount", 0)),
        rollback_performed=bool(resp.get("rollbackPerformed", False)),
        backup_ids=list(resp.get("backupIds", [])),
        affected_clips=list(resp.get("affectedClips", [])),
        warnings=warns(resp),
    )
