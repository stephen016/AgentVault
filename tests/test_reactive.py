"""Tests for Reactive Coordination."""

from __future__ import annotations

import asyncio
import logging

import pytest

from agentvault import AsyncVault


@pytest.fixture
async def vault():
    v = await AsyncVault.connect("test-reactive", backend="memory")
    yield v
    await v.close()


async def _wait_for_key(vault, key, timeout=2.0, interval=0.05):
    """Helper: poll until a key exists or timeout."""
    elapsed = 0.0
    while elapsed < timeout:
        val = await vault.get(key)
        if val is not None:
            return val
        await asyncio.sleep(interval)
        elapsed += interval
    return None


# 1. test_single_handler_fires
async def test_single_handler_fires(vault: AsyncVault):
    @vault.on_update("input", produces="output")
    async def handler(value, event):
        return f"processed: {value}"

    await vault.start()
    await vault.put("input", "hello", agent="test")
    result = await _wait_for_key(vault, "output")
    await vault.stop()
    assert result == "processed: hello"


# 2. test_handler_chain
async def test_handler_chain(vault: AsyncVault):
    @vault.on_update("a", produces="b")
    async def step1(value, event):
        return value + 1

    @vault.on_update("b", produces="c")
    async def step2(value, event):
        return value * 10

    await vault.start()
    await vault.put("a", 1, agent="test")
    result = await _wait_for_key(vault, "c")
    await vault.stop()
    assert result == 20  # (1+1) * 10


# 3. test_returns_none_no_write
async def test_returns_none_no_write(vault: AsyncVault):
    @vault.on_update("input", produces="output")
    async def handler(value, event):
        return None  # Should not write

    await vault.start()
    await vault.put("input", "data", agent="test")
    await asyncio.sleep(0.2)
    result = await vault.get("output")
    await vault.stop()
    assert result is None


# 4. test_multi_key_watch
async def test_multi_key_watch(vault: AsyncVault):
    calls = []

    @vault.on_update(["x", "y"], produces="combined")
    async def handler(value, event):
        calls.append(event.key)
        return f"got: {value}"

    await vault.start()
    await vault.put("x", "hello", agent="test")
    await _wait_for_key(vault, "combined")
    await vault.put("y", "world", agent="test")
    await asyncio.sleep(0.2)
    await vault.stop()
    assert "x" in calls
    assert "y" in calls


# 5. test_multi_key_join
async def test_multi_key_join(vault: AsyncVault):
    @vault.on_update(["a", "b"], produces="merged")
    async def handler(vault_ref, event):
        a = await vault_ref.get("a")
        b = await vault_ref.get("b")
        if a is not None and b is not None:
            return {"merged": [a, b]}
        return None

    await vault.start()
    await vault.put("a", "alpha", agent="test")
    await asyncio.sleep(0.2)
    assert await vault.get("merged") is None  # b not ready yet

    await vault.put("b", "beta", agent="test")
    result = await _wait_for_key(vault, "merged")
    await vault.stop()
    assert result == {"merged": ["alpha", "beta"]}


# 6. test_handler_error_doesnt_crash
async def test_handler_error_doesnt_crash(vault: AsyncVault, caplog):
    @vault.on_update("bad", produces="output")
    async def bad_handler(value, event):
        raise RuntimeError("intentional error")

    @vault.on_update("good", produces="good_output")
    async def good_handler(value, event):
        return "ok"

    await vault.start()
    with caplog.at_level(logging.ERROR):
        await vault.put("bad", "data", agent="test")
        await asyncio.sleep(0.2)

    # Engine should still be running
    await vault.put("good", "data", agent="test")
    result = await _wait_for_key(vault, "good_output")
    await vault.stop()
    assert result == "ok"
    assert "intentional error" in caplog.text


# 7. test_loop_detection
async def test_loop_detection(vault: AsyncVault, caplog):
    # Create a chain: a -> b -> c -> d -> ... that would loop if unchecked
    # With max_depth=3, it should stop
    engine = vault._ensure_reactive()
    engine._max_depth = 3

    @vault.on_update("step0", produces="step1")
    async def h0(value, event):
        return value

    @vault.on_update("step1", produces="step2")
    async def h1(value, event):
        return value

    @vault.on_update("step2", produces="step3")
    async def h2(value, event):
        return value

    @vault.on_update("step3", produces="step4")
    async def h3(value, event):
        return value

    await vault.start()
    with caplog.at_level(logging.ERROR):
        await vault.put("step0", "data", agent="test")
        await asyncio.sleep(0.5)
    await vault.stop()

    # step3 should exist (depth 2 -> 3 is ok since max is 3)
    # step4 should not exist (depth 3 -> 4 would exceed max_depth=3)
    assert await vault.get("step3") is not None
    assert await vault.get("step4") is None


# 8. test_self_loop_rejected
async def test_self_loop_rejected(vault: AsyncVault):
    with pytest.raises(ValueError, match="Self-loop"):
        @vault.on_update("x", produces="x")
        async def handler(value, event):
            return value


# 9. test_detect_cycles
async def test_detect_cycles(vault: AsyncVault):
    engine = vault._ensure_reactive()
    engine.register("a", "b", lambda v, e: v, name="h1")
    engine.register("b", "c", lambda v, e: v, name="h2")
    engine.register("c", "a", lambda v, e: v, name="h3")

    cycles = engine.detect_cycles()
    assert len(cycles) > 0
    # The cycle should contain a, b, c
    cycle_keys = set()
    for cycle in cycles:
        cycle_keys.update(cycle)
    assert {"a", "b", "c"}.issubset(cycle_keys)


# 10. test_start_stop
async def test_start_stop(vault: AsyncVault):
    engine = vault._ensure_reactive()
    assert not engine._running

    await vault.start()
    assert engine._running
    assert engine._task is not None

    await vault.stop()
    assert not engine._running
    assert engine._task is None


# 11. test_get_graph
async def test_get_graph(vault: AsyncVault):
    @vault.on_update("input", produces="output")
    async def my_handler(value, event):
        return value

    engine = vault._ensure_reactive()
    graph = engine.get_graph()
    assert "my_handler" in graph
    assert graph["my_handler"]["watches"] == ["input"]
    assert graph["my_handler"]["produces"] == "output"


# 12. test_delete_ignored
async def test_delete_ignored(vault: AsyncVault):
    calls = []

    @vault.on_update("key", produces="output")
    async def handler(value, event):
        calls.append(event.event_type)
        return "triggered"

    await vault.start()
    await vault.put("key", "data", agent="test")
    await _wait_for_key(vault, "output")

    calls.clear()
    await vault.delete("key")
    await asyncio.sleep(0.2)
    await vault.stop()
    # Handler should NOT have fired for delete
    assert "delete" not in calls


# 13. test_handler_agent_attribution
async def test_handler_agent_attribution(vault: AsyncVault):
    @vault.on_update("input", produces="output")
    async def summarizer(value, event):
        return "summary"

    await vault.start()
    await vault.put("input", "data", agent="test")
    await _wait_for_key(vault, "output")
    await vault.stop()

    entry = await vault.get_entry("output")
    assert entry is not None
    assert entry.agent == "summarizer"


# 14. test_concurrent_handlers
async def test_concurrent_handlers(vault: AsyncVault):
    @vault.on_update("trigger", produces="out_a")
    async def handler_a(value, event):
        await asyncio.sleep(0.05)
        return "a"

    @vault.on_update("trigger", produces="out_b")
    async def handler_b(value, event):
        await asyncio.sleep(0.05)
        return "b"

    await vault.start()
    await vault.put("trigger", "go", agent="test")

    a = await _wait_for_key(vault, "out_a")
    b = await _wait_for_key(vault, "out_b")
    await vault.stop()
    assert a == "a"
    assert b == "b"


# 15. test_handler_timeout
async def test_handler_timeout(vault: AsyncVault, caplog):
    """Handlers that exceed timeout should be cancelled and logged."""
    engine = vault._ensure_reactive()
    engine._handler_timeout = 0.2  # 200ms timeout

    @vault.on_update("slow_input", produces="slow_output")
    async def slow_handler(value, event):
        await asyncio.sleep(5.0)  # Way longer than timeout
        return "should not reach"

    await vault.start()
    with caplog.at_level(logging.ERROR):
        await vault.put("slow_input", "data", agent="test")
        await asyncio.sleep(0.5)
    await vault.stop()

    assert await vault.get("slow_output") is None
    assert "timed out" in caplog.text


# 16. test_handler_with_type_annotated_vault
async def test_handler_with_type_annotated_vault(vault: AsyncVault):
    """Handler with type-annotated vault param should receive vault reference."""
    @vault.on_update("input", produces="output")
    async def handler(v: AsyncVault, event):
        val = await v.get("input")
        return f"read: {val}"

    await vault.start()
    await vault.put("input", "hello", agent="test")
    result = await _wait_for_key(vault, "output")
    await vault.stop()
    assert result == "read: hello"


# 17. test_handler_with_short_param_name
async def test_handler_with_short_param_name(vault: AsyncVault):
    """Handler with param named 'v' should receive vault reference."""
    @vault.on_update("input", produces="output")
    async def handler(v, event):
        val = await v.get("input")
        return f"via v: {val}"

    await vault.start()
    await vault.put("input", "world", agent="test")
    result = await _wait_for_key(vault, "output")
    await vault.stop()
    assert result == "via v: world"
