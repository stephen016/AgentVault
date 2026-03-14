"""Tests for the sync Vault API."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agentvault import ConflictError, Vault


class SampleModel(BaseModel):
    name: str
    score: float
    tags: list[str] = []


def test_put_and_get(vault: Vault) -> None:
    vault.put("key1", {"hello": "world"}, agent="tester")
    assert vault.get("key1") == {"hello": "world"}


def test_get_missing_returns_none(vault: Vault) -> None:
    assert vault.get("nonexistent") is None


def test_get_with_default(vault: Vault) -> None:
    assert vault.get("nonexistent", default=42) == 42


def test_get_with_pydantic_model(vault: Vault) -> None:
    vault.put("model", SampleModel(name="test", score=0.95, tags=["a", "b"]))
    result = vault.get("model", model=SampleModel)
    assert isinstance(result, SampleModel)
    assert result.name == "test"
    assert result.score == 0.95
    assert result.tags == ["a", "b"]


def test_put_overwrites(vault: Vault) -> None:
    vault.put("key", "first")
    vault.put("key", "second")
    assert vault.get("key") == "second"


def test_delete_existing(vault: Vault) -> None:
    vault.put("key", "value")
    assert vault.delete("key") is True
    assert vault.get("key") is None


def test_delete_missing(vault: Vault) -> None:
    assert vault.delete("nonexistent") is False


def test_keys_all(vault: Vault) -> None:
    vault.put("a", 1)
    vault.put("b", 2)
    vault.put("c", 3)
    assert sorted(vault.keys()) == ["a", "b", "c"]


def test_keys_by_pattern(vault: Vault) -> None:
    vault.put("research_a", 1, agent="r")
    vault.put("research_b", 2, agent="r")
    vault.put("summary", 3, agent="s")
    assert sorted(vault.keys(pattern="research_*")) == ["research_a", "research_b"]


def test_keys_by_agent(vault: Vault) -> None:
    vault.put("a", 1, agent="alice")
    vault.put("b", 2, agent="bob")
    vault.put("c", 3, agent="alice")
    assert sorted(vault.keys(agent="alice")) == ["a", "c"]


def test_version_increments(vault: Vault) -> None:
    vault.put("key", "v1")
    entry1 = vault.get_entry("key")
    assert entry1 is not None
    assert entry1.version == 1

    vault.put("key", "v2")
    entry2 = vault.get_entry("key")
    assert entry2 is not None
    assert entry2.version == 2

    vault.put("key", "v3")
    entry3 = vault.get_entry("key")
    assert entry3 is not None
    assert entry3.version == 3


def test_agent_attribution(vault: Vault) -> None:
    vault.put("key", "value", agent="my-agent")
    entry = vault.get_entry("key")
    assert entry is not None
    assert entry.agent == "my-agent"


def test_metadata_roundtrip(vault: Vault) -> None:
    vault.put("key", "value", metadata={"source": "test", "priority": 1})
    entry = vault.get_entry("key")
    assert entry is not None
    assert entry.metadata["source"] == "test"
    assert entry.metadata["priority"] == 1


def test_context_manager(tmp_path: object) -> None:
    with Vault("test", backend="memory") as v:
        v.put("key", "value")
        assert v.get("key") == "value"


def test_clear(vault: Vault) -> None:
    vault.put("a", 1)
    vault.put("b", 2)
    vault.put("c", 3)
    count = vault.clear()
    assert count == 3
    assert vault.keys() == []


def test_cas_success(vault: Vault) -> None:
    vault.put("key", "v1")
    vault.put("key", "v2", expected_version=1)
    assert vault.get("key") == "v2"


def test_cas_conflict_raises(vault: Vault) -> None:
    vault.put("key", "v1")
    with pytest.raises(ConflictError) as exc_info:
        vault.put("key", "v2", expected_version=99)
    assert exc_info.value.expected == 99
    assert exc_info.value.actual == 1


def test_as_agent_context(vault: Vault) -> None:
    with vault.as_agent("researcher") as v:
        v.put("notes", "some notes")

    entry = vault.get_entry("notes")
    assert entry is not None
    assert entry.agent == "researcher"


def test_as_agent_restores_default(vault: Vault) -> None:
    vault.put("before", "val", agent="explicit")
    with vault.as_agent("researcher") as v:
        v.put("during", "val")
    vault.put("after", "val")

    assert vault.get_entry("before") is not None
    assert vault.get_entry("before").agent == "explicit"  # type: ignore[union-attr]
    assert vault.get_entry("during") is not None
    assert vault.get_entry("during").agent == "researcher"  # type: ignore[union-attr]
    assert vault.get_entry("after") is not None
    assert vault.get_entry("after").agent is None  # type: ignore[union-attr]


def test_put_various_types(vault: Vault) -> None:
    vault.put("str", "hello")
    vault.put("int", 42)
    vault.put("float", 3.14)
    vault.put("bool", True)
    vault.put("none", None)
    vault.put("list", [1, 2, 3])
    vault.put("dict", {"nested": {"deep": True}})

    assert vault.get("str") == "hello"
    assert vault.get("int") == 42
    assert vault.get("float") == 3.14
    assert vault.get("bool") is True
    assert vault.get("none") is None
    assert vault.get("list") == [1, 2, 3]
    assert vault.get("dict") == {"nested": {"deep": True}}


def test_get_entry_missing(vault: Vault) -> None:
    assert vault.get_entry("nonexistent") is None
