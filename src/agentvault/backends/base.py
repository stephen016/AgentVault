"""Abstract base class for AgentVault storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentvault.types import Entry


class Backend(ABC):
    """Abstract base for all storage backends.

    All methods are async. The sync Vault class wraps these via asyncio.
    """

    @abstractmethod
    async def put(
        self,
        key: str,
        value_json: str,
        type_hint: str | None,
        *,
        agent: str | None = None,
        metadata: dict[str, Any] | None = None,
        expected_version: int | None = None,
        ttl: int | None = None,
    ) -> Entry:
        """Store a value. Returns the created/updated Entry.

        Args:
            key: The key to store under.
            value_json: JSON-serialized value.
            type_hint: Optional type hint for deserialization (e.g. Pydantic class name).
            agent: Agent identifier for attribution.
            metadata: Optional metadata dict.
            expected_version: If set, raises ConflictError if current version doesn't match.
            ttl: Time-to-live in seconds. None means no expiration.

        Returns:
            The Entry that was created or updated.

        Raises:
            ConflictError: If expected_version doesn't match current version.
        """
        ...

    @abstractmethod
    async def get(self, key: str) -> tuple[str, str | None, Entry] | None:
        """Retrieve a value by key.

        Returns:
            Tuple of (json_string, type_hint, entry) or None if not found.
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        ...

    @abstractmethod
    async def keys(
        self,
        *,
        pattern: str | None = None,
        agent: str | None = None,
    ) -> list[str]:
        """List keys with optional filters.

        Args:
            pattern: Glob-style pattern (e.g. "research_*").
            agent: Filter by agent name.
        """
        ...

    @abstractmethod
    async def history(self, key: str, *, limit: int = 100) -> list[Entry]:
        """Return version history for a key, newest first."""
        ...

    @abstractmethod
    async def clear(self) -> int:
        """Delete all entries. Returns count deleted."""
        ...

    async def close(self) -> None:
        """Clean up resources. Override in subclasses if needed."""
        pass
