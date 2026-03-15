"""Tests for Semantic Conflict Resolution / Merge Strategies."""

from __future__ import annotations

import pytest

from agentvault import AsyncVault, ConflictError, Vault
from agentvault.merge import dict_deep_merge, last_write_wins, list_append


@pytest.fixture
async def vault():
    v = await AsyncVault.connect("test-merge", backend="memory")
    yield v
    await v.close()


# --- Built-in strategy unit tests ---

# 1. last_write_wins returns new value
def test_last_write_wins():
    assert last_write_wins("k", "old", "new") == "new"
    assert last_write_wins("k", [1, 2], [3, 4]) == [3, 4]


# 2. list_append merges and deduplicates
def test_list_append_basic():
    result = list_append("k", ["a", "b"], ["b", "c"])
    assert result == ["a", "b", "c"]


# 3. list_append with non-list falls back
def test_list_append_non_list():
    assert list_append("k", "old", "new") == "new"
    assert list_append("k", [1], "new") == "new"


# 4. list_append preserves order
def test_list_append_order():
    result = list_append("k", [3, 1, 2], [2, 4, 1])
    assert result == [3, 1, 2, 4]


# 5. dict_deep_merge basic
def test_dict_deep_merge_basic():
    result = dict_deep_merge("k", {"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


# 6. dict_deep_merge override on conflict
def test_dict_deep_merge_override():
    result = dict_deep_merge("k", {"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert result == {"a": 1, "b": 3, "c": 4}


# 7. dict_deep_merge recursive
def test_dict_deep_merge_recursive():
    old = {"config": {"debug": True, "level": 1}, "name": "old"}
    new = {"config": {"level": 2, "verbose": False}, "name": "new"}
    result = dict_deep_merge("k", old, new)
    assert result == {
        "config": {"debug": True, "level": 2, "verbose": False},
        "name": "new",
    }


# 8. dict_deep_merge merges nested lists
def test_dict_deep_merge_nested_lists():
    old = {"tags": ["python", "rust"]}
    new = {"tags": ["rust", "go"]}
    result = dict_deep_merge("k", old, new)
    assert result == {"tags": ["python", "rust", "go"]}


# 9. dict_deep_merge non-dict falls back
def test_dict_deep_merge_non_dict():
    assert dict_deep_merge("k", "old", "new") == "new"


# --- Integration tests: merge on conflict ---

# 10. Without merge strategy, conflict raises error
async def test_conflict_without_strategy_raises(vault: AsyncVault):
    await vault.put("key", "v1", agent="a")
    with pytest.raises(ConflictError):
        await vault.put("key", "v2", agent="b", expected_version=99)


# 11. With merge strategy, conflict auto-resolves
async def test_list_append_on_conflict(vault: AsyncVault):
    vault.set_merge_strategy("findings", "list_append")

    await vault.put("findings", ["paper1"], agent="researcher-a")
    entry = await vault.get_entry("findings")

    # Simulate conflict: agent B has stale version
    result = await vault.put(
        "findings", ["paper2", "paper3"],
        agent="researcher-b",
        expected_version=entry.version - 1,  # wrong version → conflict → merge
    )
    assert sorted(result.value) == ["paper1", "paper2", "paper3"]


# 12. dict_deep_merge on conflict
async def test_dict_merge_on_conflict(vault: AsyncVault):
    vault.set_merge_strategy("config", "dict_deep_merge")

    await vault.put("config", {"debug": True, "port": 8080}, agent="admin-a")

    result = await vault.put(
        "config", {"port": 9090, "workers": 4},
        agent="admin-b",
        expected_version=0,  # wrong version → conflict → merge
    )
    assert result.value == {"debug": True, "port": 9090, "workers": 4}


# 13. Custom merge function
async def test_custom_merge_function(vault: AsyncVault):
    def sum_merge(key, old_value, new_value):
        return old_value + new_value

    vault.set_merge_strategy("counter", sum_merge)

    await vault.put("counter", 10, agent="a")
    result = await vault.put(
        "counter", 5, agent="b", expected_version=0,
    )
    assert result.value == 15


# 14. Default merge strategy applies to all keys
async def test_default_merge_strategy(vault: AsyncVault):
    vault.set_merge_strategy(None, "last_write_wins")

    await vault.put("any_key", "old", agent="a")
    result = await vault.put(
        "any_key", "new", agent="b", expected_version=0,
    )
    assert result.value == "new"


# 15. Per-key strategy overrides default
async def test_per_key_overrides_default(vault: AsyncVault):
    vault.set_merge_strategy(None, "last_write_wins")
    vault.set_merge_strategy("items", "list_append")

    await vault.put("items", ["a"], agent="x")
    result = await vault.put(
        "items", ["b"], agent="y", expected_version=0,
    )
    # Should use list_append, not last_write_wins
    assert sorted(result.value) == ["a", "b"]


# 16. No merge strategy + no expected_version = no conflict (normal overwrite)
async def test_normal_put_no_conflict(vault: AsyncVault):
    vault.set_merge_strategy("key", "list_append")
    await vault.put("key", "v1", agent="a")
    # No expected_version means no CAS, so no conflict
    entry = await vault.put("key", "v2", agent="b")
    assert entry.value == "v2"


# 17. Unknown strategy name raises ValueError
async def test_unknown_strategy_raises(vault: AsyncVault):
    with pytest.raises(ValueError, match="Unknown merge strategy"):
        vault.set_merge_strategy("key", "nonexistent")


# 18. Sync vault merge
def test_sync_merge():
    with Vault("test-sync-merge", backend="memory") as vault:
        vault.set_merge_strategy("items", "list_append")
        vault.put("items", ["a", "b"], agent="x")
        result = vault.put(
            "items", ["c"], agent="y", expected_version=0,
        )
        assert sorted(result.value) == ["a", "b", "c"]
