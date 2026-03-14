"""Exceptions for AgentVault."""

from __future__ import annotations


class AgentVaultError(Exception):
    """Base exception for AgentVault."""


class ConflictError(AgentVaultError):
    """Raised when expected_version does not match current version."""

    def __init__(self, key: str, expected: int, actual: int) -> None:
        self.key = key
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Version conflict on key '{key}': expected {expected}, got {actual}"
        )


class LockError(AgentVaultError):
    """Raised when a lock cannot be acquired."""

    def __init__(self, key: str, holder: str | None = None) -> None:
        self.key = key
        self.holder = holder
        msg = f"Failed to acquire lock on '{key}'"
        if holder:
            msg += f" (held by '{holder}')"
        super().__init__(msg)


class SerializationError(AgentVaultError):
    """Raised when a value cannot be serialized or deserialized."""


class ContractViolationError(AgentVaultError):
    """Raised when an agent violates its declared contract."""

    def __init__(self, agent: str, key: str, reason: str) -> None:
        self.agent = agent
        self.key = key
        self.reason = reason
        super().__init__(f"Contract violation by '{agent}' on key '{key}': {reason}")


class ReactiveLoopError(AgentVaultError):
    """Raised when a reactive handler chain exceeds max depth."""

    def __init__(self, key: str, depth: int) -> None:
        self.key = key
        self.depth = depth
        super().__init__(
            f"Reactive loop detected on key '{key}': depth {depth} exceeded max"
        )
