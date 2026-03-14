"""Vault — synchronous wrapper around AsyncVault for convenience."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Generator, Type

from pydantic import BaseModel

from agentvault.async_vault import AsyncVault, _resolve_backend
from agentvault.types import Entry


class Vault:
    """Synchronous shared memory vault for AI agent coordination.

    Wraps AsyncVault for use in synchronous code. For async usage,
    use AsyncVault directly.

    Usage:
        vault = Vault("my-workflow")
        vault.put("key", {"data": 1}, agent="researcher")
        value = vault.get("key")
    """

    def __init__(
        self,
        name: str = "default",
        *,
        backend: str = "sqlite",
        path: str | None = None,
    ) -> None:
        self._name = name
        self._backend_type = backend
        self._path = path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_vault: AsyncVault | None = None
        self._default_agent: str | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run(self, coro: Any) -> Any:
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    def _ensure_vault(self) -> AsyncVault:
        if self._async_vault is None:
            resolved = _resolve_backend(self._backend_type, self._name, self._path)
            self._async_vault = AsyncVault(resolved)
        return self._async_vault

    def put(
        self,
        key: str,
        value: Any,
        *,
        agent: str | None = None,
        expected_version: int | None = None,
        ttl: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Entry:
        """Store a value in the vault. See AsyncVault.put for details."""
        effective_agent = agent if agent is not None else self._default_agent
        vault = self._ensure_vault()
        return self._run(vault.put(
            key, value, agent=effective_agent, expected_version=expected_version,
            ttl=ttl, metadata=metadata,
        ))

    def get(
        self,
        key: str,
        *,
        model: Type[BaseModel] | None = None,
        default: Any = None,
    ) -> Any:
        """Retrieve a value by key. See AsyncVault.get for details."""
        vault = self._ensure_vault()
        return self._run(vault.get(key, model=model, default=default))

    def get_entry(self, key: str) -> Entry | None:
        """Retrieve a full Entry by key. See AsyncVault.get_entry for details."""
        vault = self._ensure_vault()
        return self._run(vault.get_entry(key))

    def delete(self, key: str) -> bool:
        """Delete a key. See AsyncVault.delete for details."""
        vault = self._ensure_vault()
        return self._run(vault.delete(key))

    def keys(
        self,
        *,
        pattern: str | None = None,
        agent: str | None = None,
    ) -> list[str]:
        """List keys. See AsyncVault.keys for details."""
        vault = self._ensure_vault()
        return self._run(vault.keys(pattern=pattern, agent=agent))

    def history(self, key: str, *, limit: int = 100) -> list[Entry]:
        """Return version history for a key. See AsyncVault.history for details."""
        vault = self._ensure_vault()
        return self._run(vault.history(key, limit=limit))

    def clear(self) -> int:
        """Delete all entries. See AsyncVault.clear for details."""
        vault = self._ensure_vault()
        return self._run(vault.clear())

    @contextmanager
    def as_agent(self, agent: str) -> Generator[Vault, None, None]:
        """Context manager that auto-tags writes with the given agent name.

        Usage:
            with vault.as_agent("researcher") as v:
                v.put("notes", "...")  # agent="researcher" implied
        """
        prev = self._default_agent
        self._default_agent = agent
        try:
            yield self
        finally:
            self._default_agent = prev

    def close(self) -> None:
        """Close the vault and release resources."""
        if self._async_vault is not None:
            self._run(self._async_vault.close())
            self._async_vault = None
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
            self._loop = None

    def __enter__(self) -> Vault:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
