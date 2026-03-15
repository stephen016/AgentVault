"""Tests for Capability-Based Access Control."""

from __future__ import annotations

import pytest

from agentvault import AsyncVault, Capability, CapabilityError, Vault


@pytest.fixture
async def vault():
    v = await AsyncVault.connect("test-capabilities", backend="memory")
    yield v
    await v.close()


# 1. Capabilities disabled by default — everything allowed
async def test_disabled_by_default(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="restricted",
        read=set(),
        write=set(),
    ))
    # Not enabled, so no enforcement
    await vault.put("key", "val", agent="restricted")
    async with vault.as_agent("restricted"):
        assert await vault.get("key") == "val"


# 2. Write allowed by capability
async def test_write_allowed(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="writer",
        read={"*"},
        write={"report", "notes"},
    ))
    vault.enable_capabilities()

    await vault.put("report", "my report", agent="writer")
    assert await vault.get("report") == "my report"


# 3. Write denied by capability
async def test_write_denied(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="writer",
        read={"*"},
        write={"report"},
    ))
    vault.enable_capabilities()

    with pytest.raises(CapabilityError, match="not allowed to write"):
        await vault.put("findings", "data", agent="writer")


# 4. Read allowed by capability
async def test_read_allowed(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="reader",
        read={"plan", "config"},
        write=set(),
    ))
    vault.enable_capabilities()

    await vault.put("plan", "research plan")  # no agent, no check
    async with vault.as_agent("reader"):
        assert await vault.get("plan") == "research plan"


# 5. Read denied by capability
async def test_read_denied(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="reader",
        read={"plan"},
        write=set(),
    ))
    vault.enable_capabilities()

    await vault.put("secret", "classified")
    async with vault.as_agent("reader"):
        with pytest.raises(CapabilityError, match="not allowed to read"):
            await vault.get("secret")


# 6. Glob patterns work for write
async def test_glob_pattern_write(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="researcher",
        read={"*"},
        write={"research_*", "scratch_*"},
    ))
    vault.enable_capabilities()

    await vault.put("research_findings", "data", agent="researcher")
    await vault.put("scratch_notes", "tmp", agent="researcher")

    with pytest.raises(CapabilityError):
        await vault.put("report", "nope", agent="researcher")


# 7. Glob patterns work for read
async def test_glob_pattern_read(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="viewer",
        read={"public_*"},
        write=set(),
    ))
    vault.enable_capabilities()

    await vault.put("public_docs", "docs")
    await vault.put("private_keys", "secret")

    async with vault.as_agent("viewer"):
        assert await vault.get("public_docs") == "docs"
        with pytest.raises(CapabilityError):
            await vault.get("private_keys")


# 8. Deny patterns override allow
async def test_deny_overrides_allow(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="worker",
        read={"*"},
        write={"*"},
        deny_write={"__lock:*", "config"},
    ))
    vault.enable_capabilities()

    await vault.put("normal_key", "ok", agent="worker")
    with pytest.raises(CapabilityError):
        await vault.put("config", "nope", agent="worker")


# 9. Unregistered agent passes all checks
async def test_unregistered_agent_passes(vault: AsyncVault):
    vault.enable_capabilities()

    # No capability registered for "unknown" — passes
    await vault.put("key", "val", agent="unknown")
    async with vault.as_agent("unknown"):
        assert await vault.get("key") == "val"


# 10. None agent passes all checks
async def test_none_agent_passes(vault: AsyncVault):
    vault.enable_capabilities()
    await vault.put("key", "val")
    assert await vault.get("key") == "val"


# 11. Revoke capability
async def test_revoke_capability(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="temp",
        read=set(),
        write={"key"},
    ))
    vault.enable_capabilities()

    await vault.put("key", "v1", agent="temp")
    assert vault.revoke_capability("temp") is True

    # After revoke, agent is unregistered — passes all checks
    await vault.put("anything", "v2", agent="temp")


# 12. Describe capabilities
async def test_describe_capabilities(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="researcher",
        read={"plan", "config"},
        write={"findings"},
    ))
    desc = vault.describe_capabilities()
    assert "researcher" in desc
    assert desc["researcher"]["read"] == ["config", "plan"]
    assert desc["researcher"]["write"] == ["findings"]


# 13. as_agent auto-tags writes
async def test_as_agent_auto_tags(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="writer",
        read={"*"},
        write={"report"},
    ))
    vault.enable_capabilities()

    async with vault.as_agent("writer"):
        entry = await vault.put("report", "my report")

    assert entry.agent == "writer"


# 14. get_entry also enforces read capability
async def test_get_entry_enforces_read(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="restricted",
        read={"allowed"},
        write=set(),
    ))
    vault.enable_capabilities()

    await vault.put("forbidden", "secret")
    async with vault.as_agent("restricted"):
        with pytest.raises(CapabilityError):
            await vault.get_entry("forbidden")


# 15. Sync vault capabilities
def test_sync_capabilities():
    with Vault("test-sync-cap", backend="memory") as vault:
        vault.grant_capability(Capability(
            agent="worker",
            read={"input"},
            write={"output"},
        ))
        vault.enable_capabilities()

        vault.put("input", "data")  # no agent, passes

        with vault.as_agent("worker") as v:
            assert v.get("input") == "data"
            v.put("output", "result")

            with pytest.raises(CapabilityError):
                v.put("forbidden", "nope")

            with pytest.raises(CapabilityError):
                v.get("secret")


# 16. Multiple agents with different capabilities
async def test_multiple_agents(vault: AsyncVault):
    vault.grant_capability(Capability(
        agent="researcher",
        read={"plan"},
        write={"findings"},
    ))
    vault.grant_capability(Capability(
        agent="writer",
        read={"findings"},
        write={"report"},
    ))
    vault.enable_capabilities()

    await vault.put("plan", "research topic")

    # Researcher can read plan, write findings
    async with vault.as_agent("researcher"):
        await vault.get("plan")
        await vault.put("findings", "data")

    # Writer can read findings, write report
    async with vault.as_agent("writer"):
        await vault.get("findings")
        await vault.put("report", "done")

    # Writer cannot read plan
    async with vault.as_agent("writer"):
        with pytest.raises(CapabilityError):
            await vault.get("plan")

    # Researcher cannot write report
    with pytest.raises(CapabilityError):
        await vault.put("report", "hijack", agent="researcher")
