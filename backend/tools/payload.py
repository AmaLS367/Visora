"""Shared normalization of raw Unity bridge payload values into typed tool-result fields."""

from collections.abc import Iterable
from typing import Any


def warns(resp: dict[str, Any]) -> list[str]:
    """Coerce a bridge response's `warnings` array to `list[str]`, tolerating a missing/None value."""
    raw = resp.get("warnings")
    if not isinstance(raw, Iterable) or isinstance(raw, str | bytes):
        return []
    return [str(w) for w in raw]


def safe_int(value: Any, default: int = 0) -> int:
    """Coerce a raw bridge number (int, float, or numeric string) to `int`; anything else is `default`."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def coerce_literal(
    value: Any,
    allowed: set[str],
    warnings: list[str],
    *,
    field: str = "value",
    fallback: str = "unknown",
) -> Any:
    """
    Map a raw bridge string onto a known vocabulary.

    A value outside `allowed` is not an error - the native analysis that produced it may have
    fully succeeded - so record a warning and return `fallback` (which callers include in their
    Literal type) instead of letting Pydantic raise ValidationError and mislabel the whole call
    as a bridge failure. Returns Any so the result drops straight into a Literal-typed field;
    Pydantic still validates it against that field's real vocabulary.
    """
    text = str(value) if value is not None else ""
    if text in allowed:
        return text
    warnings.append(f"Unexpected {field} '{text}' from Unity bridge; treated as '{fallback}'.")
    return fallback


__all__ = ["coerce_literal", "safe_int", "warns"]
