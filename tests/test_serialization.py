"""Tests for serialization utilities."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agentvault.exceptions import SerializationError
from agentvault.serialization import deserialize, serialize


class MyModel(BaseModel):
    name: str
    value: int


def test_serialize_dict() -> None:
    data, hint = serialize({"key": "value"})
    assert hint is None
    result = deserialize(data, hint)
    assert result == {"key": "value"}


def test_serialize_list() -> None:
    data, hint = serialize([1, 2, 3])
    assert hint is None
    assert deserialize(data, hint) == [1, 2, 3]


def test_serialize_string() -> None:
    data, hint = serialize("hello")
    assert deserialize(data, hint) == "hello"


def test_serialize_int() -> None:
    data, hint = serialize(42)
    assert deserialize(data, hint) == 42


def test_serialize_float() -> None:
    data, hint = serialize(3.14)
    assert deserialize(data, hint) == 3.14


def test_serialize_bool() -> None:
    data, hint = serialize(True)
    assert deserialize(data, hint) is True


def test_serialize_none() -> None:
    data, hint = serialize(None)
    assert deserialize(data, hint) is None


def test_serialize_pydantic() -> None:
    model = MyModel(name="test", value=42)
    data, hint = serialize(model)
    assert hint is not None
    assert "MyModel" in hint

    # Without model param — returns dict
    result = deserialize(data, hint)
    assert isinstance(result, dict)
    assert result["name"] == "test"

    # With model param — returns typed object
    result_typed = deserialize(data, hint, model=MyModel)
    assert isinstance(result_typed, MyModel)
    assert result_typed.name == "test"
    assert result_typed.value == 42


def test_serialize_unsupported_type() -> None:
    with pytest.raises(SerializationError):
        serialize(object())


def test_deserialize_invalid_json() -> None:
    with pytest.raises(SerializationError):
        deserialize("not valid json{{{", None)
