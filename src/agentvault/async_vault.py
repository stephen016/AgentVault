"""AsyncVault — the primary async API for AgentVault."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Type

if TYPE_CHECKING:
    from agentvault.reactive import ReactiveEngine

from pydantic import BaseModel

from agentvault.backends.base import Backend
from agentvault.contracts import ContractRegistry, EnforcementMode
from agentvault.serialization import deserialize, serialize
from agentvault.types import AgentContract, Entry, WatchEvent


class AsyncVault:
    """Async shared memory vault for AI agent coordination.

    This is the primary API. For sync usage, use Vault instead.

    Usage:
        vault = await AsyncVault.connect("my-workflow")
        await vault.put("key", {"data": 1}, agent="researcher")
        value = await vault.get("key")
    """

    def __init__(self, backend: Backend) -> None:
        self._backend = backend
        self._watchers: list[asyncio.Queue[WatchEvent | None]] = []
        self._contracts = ContractRegistry()
        self._reactive: ReactiveEngine | None = None

    @classmethod
    async def connect(
        cls,
        name: str = "default",
        *,
        backend: str | Backend = "sqlite",
        path: str | None = None,
    ) -> AsyncVault:
        """Create and connect an AsyncVault.

        Args:
            name: Vault name (used for database file naming).
            backend: Backend type ("sqlite", "memory") or a Backend instance.
            path: Override default storage path (for sqlite).
        """
        resolved = _resolve_backend(backend, name, path)
        return cls(resolved)

    # --- Contract Methods ---

    def register_agent(self, contract: AgentContract) -> None:
        """Register an agent contract for validation."""
        self._contracts.register(contract)

    def set_enforcement(self, mode: EnforcementMode) -> None:
        """Set contract enforcement mode: 'strict', 'warn', or 'off'."""
        self._contracts.enforcement = mode

    def get_dependency_graph(self) -> dict:
        """Return the agent dependency graph."""
        return self._contracts.get_dependency_graph()

    def validate_contracts(self) -> list[str]:
        """Check for structural issues across all registered contracts."""
        return self._contracts.validate_contracts()

    # --- Reactive Methods ---

    def _ensure_reactive(self) -> ReactiveEngine:
        if self._reactive is None:
            from agentvault.reactive import ReactiveEngine
            self._reactive = ReactiveEngine(self)
        return self._reactive

    def on_update(
        self,
        watches: str | list[str],
        *,
        produces: str,
        name: str | None = None,
    ) -> Callable:
        """Decorator to register a reactive handler.

        Usage:
            @vault.on_update("research_findings", produces="summary")
            async def summarize(value, event):
                return await llm.call("Summarize: " + str(value))
        """
        engine = self._ensure_reactive()
        return engine.on_update(watches, produces=produces, name=name)

    async def start(self) -> None:
        """Start the reactive engine."""
        if self._reactive is not None:
            await self._reactive.start()

    async def stop(self) -> None:
        """Stop the reactive engine."""
        if self._reactive is not None:
            await self._reactive.stop()

    # --- Core Methods ---

    async def put(
        self,
        key: str,
        value: Any,
        *,
        agent: str | None = None,
        expected_version: int | None = None,
        ttl: int | None = None,
        metadata: dict[str, Any] | None = None,
        _trigger_depth: int = 0,
    ) -> Entry:
        """Store a value in the vault.

        Args:
            key: The key to store under.
            value: Any JSON-serializable value or Pydantic BaseModel.
            agent: Agent identifier for attribution.
            expected_version: For compare-and-swap. Raises ConflictError on mismatch.
            ttl: Time-to-live in seconds. None means no expiration.
            metadata: Optional metadata dict.
            _trigger_depth: Internal — tracks reactive chain depth.

        Returns:
            The Entry that was created or updated.
        """
        # Validate against agent contracts
        self._contracts.validate_put(agent, key, value)

        value_json, type_hint = serialize(value)

        # Get old value for watch notification
        old_result = await self._backend.get(key)
        old_value = None
        if old_result is not None:
            old_value = deserialize(old_result[0], old_result[1])

        entry = await self._backend.put(
            key,
            value_json,
            type_hint,
            agent=agent,
            metadata=metadata,
            expected_version=expected_version,
            ttl=ttl,
        )

        # Notify watchers
        event = WatchEvent(
            key=key,
            new_value=entry.value,
            old_value=old_value,
            agent=agent,
            version=entry.version,
            event_type="put",
        )
        event._trigger_depth = _trigger_depth
        await self._notify(event)

        return entry

    async def get(
        self,
        key: str,
        *,
        model: Type[BaseModel] | None = None,
        default: Any = None,
    ) -> Any:
        """Retrieve a value by key.

        Args:
            key: The key to look up.
            model: Optional Pydantic model class for typed deserialization.
            default: Value to return if key is not found.

        Returns:
            The deserialized value, or default if not found.
        """
        result = await self._backend.get(key)
        if result is None:
            return default
        value_json, type_hint, _ = result
        return deserialize(value_json, type_hint, model=model)

    async def get_entry(self, key: str) -> Entry | None:
        """Retrieve a full Entry (value + metadata) by key.

        Returns None if key is not found.
        """
        result = await self._backend.get(key)
        if result is None:
            return None
        return result[2]

    async def delete(self, key: str) -> bool:
        """Delete a key from the vault.

        Returns True if the key existed, False otherwise.
        """
        # Get old value for watch notification
        old_result = await self._backend.get(key)

        deleted = await self._backend.delete(key)

        if deleted and old_result is not None:
            old_entry = old_result[2]
            old_value = deserialize(old_result[0], old_result[1])
            await self._notify(WatchEvent(
                key=key,
                new_value=None,
                old_value=old_value,
                agent=old_entry.agent,
                version=old_entry.version + 1,
                event_type="delete",
            ))

        return deleted

    async def keys(
        self,
        *,
        pattern: str | None = None,
        agent: str | None = None,
    ) -> list[str]:
        """List keys in the vault.

        Args:
            pattern: Glob-style pattern (e.g. "research_*").
            agent: Filter by agent name.
        """
        return await self._backend.keys(pattern=pattern, agent=agent)

    async def history(self, key: str, *, limit: int = 100) -> list[Entry]:
        """Return version history for a key, newest first."""
        return await self._backend.history(key, limit=limit)

    async def clear(self) -> int:
        """Delete all entries in the vault. Returns count deleted."""
        return await self._backend.clear()

    async def watch(
        self,
        keys: str | list[str] | None = None,
    ) -> AsyncIterator[WatchEvent]:
        """Watch for changes to keys in the vault.

        Args:
            keys: Key or list of keys to watch. None watches all keys.

        Yields:
            WatchEvent for each change.

        Usage:
            async for event in vault.watch("findings"):
                print(event.key, event.new_value)
        """
        if isinstance(keys, str):
            keys = [keys]

        queue = self._add_watcher()

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                if keys is None or event.key in keys:
                    yield event
        finally:
            self._remove_watcher(queue)

    def _add_watcher(self, maxsize: int = 1000) -> asyncio.Queue[WatchEvent | None]:
        """Register a new watcher queue. Used by watch() and ReactiveEngine."""
        queue: asyncio.Queue[WatchEvent | None] = asyncio.Queue(maxsize=maxsize)
        self._watchers.append(queue)
        return queue

    def _remove_watcher(self, queue: asyncio.Queue[WatchEvent | None]) -> None:
        """Unregister a watcher queue."""
        if queue in self._watchers:
            self._watchers.remove(queue)

    async def _notify(self, event: WatchEvent) -> None:
        """Notify all watchers of a change."""
        for queue in self._watchers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest event to make room (backpressure)
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def close(self) -> None:
        """Close the vault and release resources."""
        # Stop reactive engine first
        await self.stop()
        # Signal all watchers to stop
        for queue in self._watchers:
            await queue.put(None)
        self._watchers.clear()
        await self._backend.close()

    async def __aenter__(self) -> AsyncVault:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


def _resolve_backend(backend: str | Backend, vault_name: str, path: str | None) -> Backend:
    """Resolve a backend string or instance to a Backend object."""
    if isinstance(backend, Backend):
        return backend

    if backend == "sqlite":
        from agentvault.backends.sqlite import SQLiteBackend
        return SQLiteBackend(vault_name=vault_name, path=path)
    elif backend == "memory":
        from agentvault.backends.memory import MemoryBackend
        return MemoryBackend()
    else:
        raise ValueError(
            f"Unknown backend: '{backend}'. Supported: 'sqlite', 'memory'"
        )
