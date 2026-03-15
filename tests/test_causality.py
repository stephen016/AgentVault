"""Tests for Causal Ordering / Vector Clocks."""

from __future__ import annotations

import pytest

from agentvault import AsyncVault, Vault, get_causal_deps


@pytest.fixture
async def vault():
    v = await AsyncVault.connect("test-causality", backend="memory")
    yield v
    await v.close()


# 1. Basic causal tracking: get then put records dependency
async def test_basic_causal_tracking(vault: AsyncVault):
    await vault.put("plan", "research RAG", agent="planner")

    async with vault.track_causality():
        plan = await vault.get("plan")
        entry = await vault.put("findings", {"topic": plan}, agent="researcher")

    deps = get_causal_deps(entry)
    assert deps == {"plan": 1}


# 2. Multiple reads create multiple dependencies
async def test_multiple_reads(vault: AsyncVault):
    await vault.put("data_a", "alpha", agent="source")
    await vault.put("data_b", "beta", agent="source")

    async with vault.track_causality():
        a = await vault.get("data_a")
        b = await vault.get("data_b")
        entry = await vault.put("combined", f"{a}+{b}", agent="merger")

    deps = get_causal_deps(entry)
    assert deps == {"data_a": 1, "data_b": 1}


# 3. No tracking context = no causal deps
async def test_no_tracking_no_deps(vault: AsyncVault):
    await vault.put("input", "data", agent="source")
    await vault.get("input")
    entry = await vault.put("output", "result", agent="worker")

    deps = get_causal_deps(entry)
    assert deps == {}


# 4. Reading updated key tracks latest version
async def test_tracks_latest_version(vault: AsyncVault):
    await vault.put("key", "v1", agent="source")
    await vault.put("key", "v2", agent="source")
    await vault.put("key", "v3", agent="source")

    async with vault.track_causality():
        await vault.get("key")  # should record version 3
        entry = await vault.put("derived", "from v3", agent="worker")

    deps = get_causal_deps(entry)
    assert deps == {"key": 3}


# 5. is_stale returns False when deps are current
async def test_is_stale_false_when_current(vault: AsyncVault):
    await vault.put("input", "data", agent="source")

    async with vault.track_causality():
        await vault.get("input")
        await vault.put("output", "result", agent="worker")

    assert await vault.is_stale("output") is False


# 6. is_stale returns True when dep has been updated
async def test_is_stale_true_when_dep_updated(vault: AsyncVault):
    await vault.put("input", "data", agent="source")

    async with vault.track_causality():
        await vault.get("input")
        await vault.put("output", "result", agent="worker")

    # Update the dependency
    await vault.put("input", "new data", agent="source")

    assert await vault.is_stale("output") is True


# 7. is_stale returns True when dep has been deleted
async def test_is_stale_true_when_dep_deleted(vault: AsyncVault):
    await vault.put("input", "data", agent="source")

    async with vault.track_causality():
        await vault.get("input")
        await vault.put("output", "result", agent="worker")

    await vault.delete("input")
    assert await vault.is_stale("output") is True


# 8. is_stale returns False for entry with no deps
async def test_is_stale_false_no_deps(vault: AsyncVault):
    await vault.put("standalone", "data", agent="source")
    assert await vault.is_stale("standalone") is False


# 9. causal_chain returns full provenance
async def test_causal_chain(vault: AsyncVault):
    await vault.put("plan", "research topic", agent="planner")

    async with vault.track_causality():
        await vault.get("plan")
        await vault.put("findings", {"results": []}, agent="researcher")

    async with vault.track_causality():
        await vault.get("findings")
        await vault.put("report", "final report", agent="writer")

    chain = await vault.causal_chain("report")
    assert len(chain) >= 3

    # First node should be report itself
    assert chain[0]["key"] == "report"
    assert chain[0]["causal_deps"] == {"findings": 1}

    # Should contain findings
    findings_nodes = [n for n in chain if n["key"] == "findings"]
    assert len(findings_nodes) == 1
    assert findings_nodes[0]["causal_deps"] == {"plan": 1}

    # Should contain plan
    plan_nodes = [n for n in chain if n["key"] == "plan"]
    assert len(plan_nodes) == 1


# 10. causal_chain with depth limit
async def test_causal_chain_depth_limit(vault: AsyncVault):
    # Build a 5-deep chain
    await vault.put("step0", "root", agent="source")
    for i in range(1, 5):
        async with vault.track_causality():
            await vault.get(f"step{i-1}")
            await vault.put(f"step{i}", f"derived from step{i-1}", agent="worker")

    # With depth=2, should only get step4 and step3
    chain = await vault.causal_chain("step4", depth=2)
    keys = [n["key"] for n in chain]
    assert "step4" in keys
    assert "step3" in keys
    assert "step0" not in keys  # too deep


# 11. causal_chain for nonexistent key
async def test_causal_chain_missing_key(vault: AsyncVault):
    chain = await vault.causal_chain("nonexistent")
    assert chain == []


# 12. get_entry also records causal reads
async def test_get_entry_records_read(vault: AsyncVault):
    await vault.put("source", "data", agent="producer")

    async with vault.track_causality():
        entry = await vault.get_entry("source")
        assert entry is not None
        output = await vault.put("derived", "from entry", agent="consumer")

    deps = get_causal_deps(output)
    assert deps == {"source": 1}


# 13. Multiple puts within same tracking context share deps
async def test_multiple_puts_share_deps(vault: AsyncVault):
    await vault.put("input", "data", agent="source")

    async with vault.track_causality():
        await vault.get("input")
        e1 = await vault.put("out_a", "a", agent="worker")
        e2 = await vault.put("out_b", "b", agent="worker")

    # Both outputs should depend on input
    assert get_causal_deps(e1) == {"input": 1}
    assert get_causal_deps(e2) == {"input": 1}


# 14. Sync vault causal tracking
def test_sync_causal_tracking():
    with Vault("test-sync-causality", backend="memory") as vault:
        vault.put("input", "data", agent="source")

        with vault.track_causality():
            vault.get("input")
            entry = vault.put("output", "result", agent="worker")

        deps = get_causal_deps(entry)
        assert deps == {"input": 1}


# 15. Sync vault is_stale
def test_sync_is_stale():
    with Vault("test-sync-stale", backend="memory") as vault:
        vault.put("input", "data", agent="source")

        with vault.track_causality():
            vault.get("input")
            vault.put("output", "result", agent="worker")

        assert not vault.is_stale("output")
        vault.put("input", "updated", agent="source")
        assert vault.is_stale("output")


# 16. Sync vault causal_chain
def test_sync_causal_chain():
    with Vault("test-sync-chain", backend="memory") as vault:
        vault.put("root", "data", agent="source")

        with vault.track_causality():
            vault.get("root")
            vault.put("derived", "result", agent="worker")

        chain = vault.causal_chain("derived")
        assert len(chain) == 2
        assert chain[0]["key"] == "derived"
        assert chain[1]["key"] == "root"
