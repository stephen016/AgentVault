"""Tests for coordination primitives: CAS, locks, TTL."""

from __future__ import annotations

import time

import pytest

from agentvault import AsyncVault, Vault
from agentvault.lock import VaultLock


def test_ttl_put_and_expire(vault: Vault) -> None:
    vault.put("temp", "data", ttl=1)
    assert vault.get("temp") == "data"

    time.sleep(1.1)
    assert vault.get("temp") is None


def test_ttl_keys_excludes_expired(vault: Vault) -> None:
    vault.put("permanent", "stays")
    vault.put("temp", "goes", ttl=1)
    assert sorted(vault.keys()) == ["permanent", "temp"]

    time.sleep(1.1)
    assert vault.keys() == ["permanent"]


@pytest.mark.asyncio
async def test_lock_acquire_release() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    try:
        lock = VaultLock(vault, "resource", holder="agent-1", timeout=5)
        acquired = await lock.acquire()
        assert acquired is True
        await lock.release()
    finally:
        await vault.close()


@pytest.mark.asyncio
async def test_lock_context_manager() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    try:
        lock = VaultLock(vault, "resource", holder="agent-1", timeout=5)
        async with lock:
            # Lock is held — we can work
            await vault.put("resource", "working", agent="agent-1")
        # Lock released
        result = await vault._backend.get("__lock:resource")
        assert result is None
    finally:
        await vault.close()


@pytest.mark.asyncio
async def test_lock_prevents_double_acquire() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    try:
        lock1 = VaultLock(vault, "resource", holder="agent-1", timeout=5)
        lock2 = VaultLock(vault, "resource", holder="agent-2", timeout=0.3, poll_interval=0.05)

        await lock1.acquire()
        with pytest.raises(Exception):  # LockError or timeout
            await lock2.acquire()

        await lock1.release()
    finally:
        await vault.close()


@pytest.mark.asyncio
async def test_lock_release_only_by_holder() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    try:
        lock1 = VaultLock(vault, "resource", holder="agent-1", timeout=5)
        lock2 = VaultLock(vault, "resource", holder="agent-2", timeout=5)

        await lock1.acquire()
        # Agent-2 tries to release agent-1's lock — should not succeed
        await lock2.release()

        # Lock should still exist
        result = await vault._backend.get("__lock:resource")
        assert result is not None

        await lock1.release()
    finally:
        await vault.close()
