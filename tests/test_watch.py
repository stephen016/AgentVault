"""Tests for watch/subscription functionality."""

from __future__ import annotations

import asyncio

import pytest

from agentvault import AsyncVault, WatchEvent


@pytest.mark.asyncio
async def test_watch_receives_put() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    events: list[WatchEvent] = []

    async def collector() -> None:
        async for event in vault.watch("key1"):
            events.append(event)
            if len(events) >= 1:
                break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    await vault.put("key1", "hello", agent="tester")
    await asyncio.wait_for(task, timeout=2.0)

    assert len(events) == 1
    assert events[0].key == "key1"
    assert events[0].new_value == "hello"
    assert events[0].event_type == "put"
    assert events[0].agent == "tester"

    await vault.close()


@pytest.mark.asyncio
async def test_watch_receives_delete() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    events: list[WatchEvent] = []

    await vault.put("key1", "hello")

    async def collector() -> None:
        async for event in vault.watch("key1"):
            events.append(event)
            if len(events) >= 1:
                break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    await vault.delete("key1")
    await asyncio.wait_for(task, timeout=2.0)

    assert len(events) == 1
    assert events[0].event_type == "delete"
    assert events[0].old_value == "hello"

    await vault.close()


@pytest.mark.asyncio
async def test_watch_ignores_other_keys() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    events: list[WatchEvent] = []

    async def collector() -> None:
        async for event in vault.watch("target"):
            events.append(event)
            break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    # This should NOT trigger the watcher
    await vault.put("other_key", "data")
    await asyncio.sleep(0.1)

    # This should trigger it
    await vault.put("target", "data")
    await asyncio.wait_for(task, timeout=2.0)

    assert len(events) == 1
    assert events[0].key == "target"

    await vault.close()


@pytest.mark.asyncio
async def test_watch_multiple_keys() -> None:
    vault = await AsyncVault.connect("test", backend="memory")
    events: list[WatchEvent] = []

    async def collector() -> None:
        async for event in vault.watch(["key_a", "key_b"]):
            events.append(event)
            if len(events) >= 2:
                break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    await vault.put("key_a", 1)
    await vault.put("key_c", 2)  # Should be ignored
    await vault.put("key_b", 3)

    await asyncio.wait_for(task, timeout=2.0)

    assert len(events) == 2
    assert events[0].key == "key_a"
    assert events[1].key == "key_b"

    await vault.close()


@pytest.mark.asyncio
async def test_watch_cancellation() -> None:
    vault = await AsyncVault.connect("test", backend="memory")

    async def infinite_watcher() -> None:
        async for _ in vault.watch():
            pass

    task = asyncio.create_task(infinite_watcher())
    await asyncio.sleep(0.05)

    # Closing vault should stop watchers
    await vault.close()
    await asyncio.wait_for(task, timeout=2.0)  # Should complete without timeout
