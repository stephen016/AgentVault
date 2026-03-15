"""AgentVault — Shared memory and state coordination for AI agents."""

from agentvault.async_vault import AsyncVault
from agentvault.causality import CausalContext, CausalTracker, get_causal_deps
from agentvault.contracts import ContractRegistry, EnforcementMode
from agentvault.exceptions import (
    AgentVaultError,
    ConflictError,
    ContractViolationError,
    LockError,
    ReactiveLoopError,
    SerializationError,
)
from agentvault.merge import (
    MergeRegistry,
    dict_deep_merge,
    last_write_wins,
    list_append,
)
from agentvault.reactive import ReactiveEngine
from agentvault.types import AgentContract, Entry, WatchEvent
from agentvault.vault import Vault

__version__ = "0.2.0"
__all__ = [
    "AsyncVault",
    "Vault",
    "Entry",
    "WatchEvent",
    "AgentContract",
    "AgentVaultError",
    "ConflictError",
    "ContractViolationError",
    "LockError",
    "ReactiveLoopError",
    "SerializationError",
    "ContractRegistry",
    "EnforcementMode",
    "ReactiveEngine",
    "CausalContext",
    "CausalTracker",
    "get_causal_deps",
    "MergeRegistry",
    "dict_deep_merge",
    "list_append",
    "last_write_wins",
]
