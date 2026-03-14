"""Tests for history/audit trail functionality."""

from __future__ import annotations

from agentvault import Vault


def test_history_returns_versions(vault: Vault) -> None:
    vault.put("key", "v1", agent="a")
    vault.put("key", "v2", agent="b")
    vault.put("key", "v3", agent="a")

    history = vault.history("key")
    assert len(history) == 3
    # Newest first
    assert history[0].version == 3
    assert history[1].version == 2
    assert history[2].version == 1


def test_history_order(vault: Vault) -> None:
    for i in range(5):
        vault.put("key", f"v{i}")

    history = vault.history("key")
    versions = [e.version for e in history]
    assert versions == [5, 4, 3, 2, 1]


def test_history_limit(vault: Vault) -> None:
    for i in range(10):
        vault.put("key", f"v{i}")

    history = vault.history("key", limit=3)
    assert len(history) == 3
    assert history[0].version == 10


def test_history_includes_agent(vault: Vault) -> None:
    vault.put("key", "v1", agent="alice")
    vault.put("key", "v2", agent="bob")

    history = vault.history("key")
    assert history[0].agent == "bob"
    assert history[1].agent == "alice"


def test_history_empty(vault: Vault) -> None:
    history = vault.history("nonexistent")
    assert history == []
