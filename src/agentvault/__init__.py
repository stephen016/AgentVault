"""AgentVault — Shared memory and state coordination for AI agents."""

from agentvault.async_vault import AsyncVault
from agentvault.exceptions import AgentVaultError, ConflictError, LockError, SerializationError
from agentvault.types import Entry, WatchEvent
from agentvault.vault import Vault

__version__ = "0.1.0"
__all__ = [
    "AsyncVault",
    "Vault",
    "Entry",
    "WatchEvent",
    "AgentVaultError",
    "ConflictError",
    "LockError",
    "SerializationError",
]
