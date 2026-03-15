"""Capability-Based Access Control — scoped permissions for AI agents.

Each agent gets a capability token that defines exactly which keys it can
read and write. Violations are impossible (raised before the operation
happens), not just logged.

This is security for multi-agent systems: a compromised or buggy agent
cannot read data it shouldn't see or overwrite keys it doesn't own.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import Any

from agentvault.exceptions import AgentVaultError

logger = logging.getLogger(__name__)


class CapabilityError(AgentVaultError):
    """Raised when an agent tries to perform an operation it's not allowed to."""

    def __init__(self, agent: str, operation: str, key: str) -> None:
        self.agent = agent
        self.operation = operation
        self.key = key
        super().__init__(
            f"Agent '{agent}' is not allowed to {operation} key '{key}'"
        )


@dataclass
class Capability:
    """Defines what an agent is allowed to do.

    Permissions use glob patterns for flexibility:
    - "findings" — exact key match
    - "research_*" — any key starting with research_
    - "*" — all keys

    Args:
        agent: The agent name this capability belongs to.
        read: Set of key patterns the agent can read.
        write: Set of key patterns the agent can write.
        deny_read: Set of key patterns explicitly denied for reading.
        deny_write: Set of key patterns explicitly denied for writing.
    """

    agent: str
    read: set[str] = field(default_factory=set)
    write: set[str] = field(default_factory=set)
    deny_read: set[str] = field(default_factory=set)
    deny_write: set[str] = field(default_factory=set)


class CapabilityManager:
    """Manages and enforces capability-based access control."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def grant(self, capability: Capability) -> None:
        """Grant a capability to an agent. Overwrites any existing capability."""
        self._capabilities[capability.agent] = capability

    def revoke(self, agent: str) -> bool:
        """Revoke an agent's capability. Returns True if it existed."""
        if agent in self._capabilities:
            del self._capabilities[agent]
            return True
        return False

    def check_read(self, agent: str | None, key: str) -> None:
        """Check if an agent is allowed to read a key.

        Raises CapabilityError if denied.
        Does nothing if:
        - Capabilities are not enabled
        - Agent is None (anonymous access)
        - Agent has no registered capability (unmanaged agent)
        """
        if not self._enabled or agent is None:
            return
        if agent not in self._capabilities:
            return

        cap = self._capabilities[agent]
        if not _matches_any(key, cap.read):
            raise CapabilityError(agent, "read", key)
        if _matches_any(key, cap.deny_read):
            raise CapabilityError(agent, "read", key)

    def check_write(self, agent: str | None, key: str) -> None:
        """Check if an agent is allowed to write a key.

        Raises CapabilityError if denied.
        """
        if not self._enabled or agent is None:
            return
        if agent not in self._capabilities:
            return

        cap = self._capabilities[agent]
        if not _matches_any(key, cap.write):
            raise CapabilityError(agent, "write", key)
        if _matches_any(key, cap.deny_write):
            raise CapabilityError(agent, "write", key)

    def get_capabilities(self, agent: str) -> Capability | None:
        """Get the capability for an agent, or None if not registered."""
        return self._capabilities.get(agent)

    def list_agents(self) -> list[str]:
        """List all agents with registered capabilities."""
        return list(self._capabilities.keys())

    def describe(self) -> dict[str, dict[str, Any]]:
        """Return a human-readable description of all capabilities."""
        result: dict[str, dict[str, Any]] = {}
        for agent, cap in self._capabilities.items():
            result[agent] = {
                "read": sorted(cap.read),
                "write": sorted(cap.write),
                "deny_read": sorted(cap.deny_read),
                "deny_write": sorted(cap.deny_write),
            }
        return result


def _matches_any(key: str, patterns: set[str]) -> bool:
    """Check if a key matches any of the given glob patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(key, pattern):
            return True
    return False
