"""Tests for Agent Contracts."""

from __future__ import annotations

import logging

import pytest

from agentvault import (
    AgentContract,
    AsyncVault,
    ContractViolationError,
    Vault,
)


@pytest.fixture
async def vault():
    v = await AsyncVault.connect("test-contracts", backend="memory")
    yield v
    await v.close()


# 1. test_register_agent
async def test_register_agent(vault: AsyncVault):
    vault.register_agent(AgentContract(
        name="researcher",
        produces={"findings": str},
        consumes={"plan": str},
    ))
    graph = vault.get_dependency_graph()
    assert "researcher" in graph
    assert "findings" in graph["researcher"]["produces"]


# 2. test_register_duplicate_raises
async def test_register_duplicate_raises(vault: AsyncVault):
    vault.register_agent(AgentContract(name="agent-a", produces={"x": str}))
    with pytest.raises(ValueError, match="already registered"):
        vault.register_agent(AgentContract(name="agent-a", produces={"y": int}))


# 3. test_enforcement_off_allows_anything
async def test_enforcement_off_allows_anything(vault: AsyncVault):
    vault.register_agent(AgentContract(name="writer", produces={"report": str}))
    # enforcement is "off" by default — any put should work
    entry = await vault.put("unknown_key", 42, agent="writer")
    assert entry.value == 42


# 4. test_strict_blocks_wrong_key
async def test_strict_blocks_wrong_key(vault: AsyncVault):
    vault.register_agent(AgentContract(name="writer", produces={"report": str}))
    vault.set_enforcement("strict")
    with pytest.raises(ContractViolationError, match="not in declared produces"):
        await vault.put("findings", "data", agent="writer")


# 5. test_strict_blocks_wrong_type
async def test_strict_blocks_wrong_type(vault: AsyncVault):
    vault.register_agent(AgentContract(name="writer", produces={"report": str}))
    vault.set_enforcement("strict")
    with pytest.raises(ContractViolationError, match="expected type str"):
        await vault.put("report", 42, agent="writer")


# 6. test_strict_allows_valid_put
async def test_strict_allows_valid_put(vault: AsyncVault):
    vault.register_agent(AgentContract(name="writer", produces={"report": str}))
    vault.set_enforcement("strict")
    entry = await vault.put("report", "My report", agent="writer")
    assert entry.value == "My report"


# 7. test_warn_logs_violation
async def test_warn_logs_violation(vault: AsyncVault, caplog):
    vault.register_agent(AgentContract(name="writer", produces={"report": str}))
    vault.set_enforcement("warn")
    with caplog.at_level(logging.WARNING):
        entry = await vault.put("wrong_key", "data", agent="writer")
    assert entry.value == "data"  # still succeeds
    assert "Contract violation" in caplog.text


# 8. test_unregistered_agent_allowed
async def test_unregistered_agent_allowed(vault: AsyncVault):
    vault.set_enforcement("strict")
    # No contract registered for "unknown_agent" — should pass
    entry = await vault.put("any_key", "data", agent="unknown_agent")
    assert entry.value == "data"


# 9. test_none_agent_allowed
async def test_none_agent_allowed(vault: AsyncVault):
    vault.set_enforcement("strict")
    entry = await vault.put("any_key", "data")
    assert entry.value == "data"


# 10. test_validate_missing_producer
async def test_validate_missing_producer(vault: AsyncVault):
    vault.register_agent(AgentContract(
        name="writer",
        produces={"report": str},
        consumes={"plan": str},
    ))
    issues = vault.validate_contracts()
    assert any("plan" in issue and "no agent produces" in issue for issue in issues)


# 11. test_validate_duplicate_producer
async def test_validate_duplicate_producer(vault: AsyncVault):
    vault.register_agent(AgentContract(name="a", produces={"shared": str}))
    vault.register_agent(AgentContract(name="b", produces={"shared": str}))
    issues = vault.validate_contracts()
    assert any("shared" in issue and "multiple agents" in issue for issue in issues)


# 12. test_validate_type_mismatch
async def test_validate_type_mismatch(vault: AsyncVault):
    vault.register_agent(AgentContract(name="producer", produces={"data": str}))
    vault.register_agent(AgentContract(name="consumer", consumes={"data": int}))
    issues = vault.validate_contracts()
    assert any("Type mismatch" in issue and "data" in issue for issue in issues)


# 13. test_validate_clean
async def test_validate_clean(vault: AsyncVault):
    vault.register_agent(AgentContract(
        name="producer",
        produces={"data": str},
    ))
    vault.register_agent(AgentContract(
        name="consumer",
        consumes={"data": str},
    ))
    issues = vault.validate_contracts()
    assert issues == []


# 14. test_as_agent_with_contracts
def test_as_agent_with_contracts():
    with Vault("test-sync-contracts", backend="memory") as vault:
        vault.register_agent(AgentContract(name="writer", produces={"report": str}))
        vault.set_enforcement("strict")

        with vault.as_agent("writer") as v:
            v.put("report", "My report")
            with pytest.raises(ContractViolationError):
                v.put("wrong_key", "data")


# 15. test_get_dependency_graph
async def test_get_dependency_graph(vault: AsyncVault):
    vault.register_agent(AgentContract(
        name="researcher",
        produces={"findings": str},
        consumes={"plan": str},
        description="Does research",
    ))
    vault.register_agent(AgentContract(
        name="writer",
        produces={"report": str},
        consumes={"findings": str},
    ))

    graph = vault.get_dependency_graph()
    assert len(graph) == 2
    assert graph["researcher"]["produces"] == {"findings": str}
    assert graph["researcher"]["consumes"] == {"plan": str}
    assert graph["researcher"]["description"] == "Does research"
    assert graph["writer"]["produces"] == {"report": str}
    assert graph["writer"]["consumes"] == {"findings": str}
