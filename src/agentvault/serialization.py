"""Serialization utilities for AgentVault values."""

from __future__ import annotations

import json
from typing import Any, Type

from pydantic import BaseModel

from agentvault.exceptions import SerializationError

# JSON-serializable primitive types
_PRIMITIVES = (dict, list, int, float, bool, str, type(None))


def serialize(value: Any) -> tuple[str, str | None]:
    """Serialize a value to a JSON string and an optional type hint.

    Returns:
        Tuple of (json_string, type_hint).
        type_hint is the fully qualified class name for Pydantic models, None otherwise.
    """
    if isinstance(value, BaseModel):
        type_hint = f"{value.__class__.__module__}.{value.__class__.__qualname__}"
        return value.model_dump_json(), type_hint
    if isinstance(value, _PRIMITIVES):
        try:
            return json.dumps(value), None
        except (TypeError, ValueError) as e:
            raise SerializationError(f"Cannot serialize value: {e}") from e
    raise SerializationError(
        f"Cannot serialize type {type(value).__name__}. "
        f"Supported: dict, list, str, int, float, bool, None, pydantic.BaseModel"
    )


def deserialize(
    data: str,
    type_hint: str | None = None,
    *,
    model: Type[BaseModel] | None = None,
) -> Any:
    """Deserialize a JSON string back to a Python object.

    If model is provided, validates against it regardless of type_hint.
    If type_hint indicates a Pydantic model but no model param is given,
    returns a plain dict (user can pass model= to get typed object).
    """
    try:
        if model is not None:
            return model.model_validate_json(data)
        return json.loads(data)
    except (json.JSONDecodeError, ValueError) as e:
        raise SerializationError(f"Cannot deserialize value: {e}") from e
