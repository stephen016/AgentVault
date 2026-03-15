"""AsyncVault — the primary async API for AgentVault."""

from __future__ import annotations

import asyncio
import contextvars
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Type

from pydantic import BaseModel

from agentvault.backends.base import Backend
from agentvault.capabilities import Capability, CapabilityManager
from agentvault.causality import (
    CAUSAL_DEPS_KEY,
    CausalContext,
    CausalTracker,
    get_causal_deps,
)
from agentvault.contracts import ContractRegistry, EnforcementMode
from agentvault.exceptions import ConflictError
from agentvault.merge import MergeFunction, MergeRegistry
from agentvault.serialization import deserialize, serialize
from agentvault.types import AgentContract, Entry, WatchEvent

if TYPE_CHECKING:
    from agentvault.reactive import ReactiveEngine

# Task-local active agent for capability checks on reads
_active_agent: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_active_agent", default=None
)


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
        self._causal = CausalTracker()
        self._merges = MergeRegistry()
        self._capabilities = CapabilityManager()

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

    # --- Agent Context ---

    def as_agent(self, agent: str) -> _AsyncAgentContext:
        """Async context manager that sets the active agent for operations.

        Within this context, get() enforces read capabilities and put()
        auto-tags writes with the agent name.

        Usage:
            async with vault.as_agent("researcher"):
                data = await vault.get("plan")      # read checked
                await vault.put("findings", data)    # agent auto-tagged
        """
        return _AsyncAgentContext(agent)

    # --- Capability Methods ---

    def grant_capability(self, capability: Capability) -> None:
        """Grant a capability to an agent.

        Usage:
            vault.grant_capability(Capability(
                agent="researcher",
                read={"plan", "config"},
                write={"findings", "scratch_*"},
            ))
        """
        self._capabilities.grant(capability)

    def revoke_capability(self, agent: str) -> bool:
        """Revoke an agent's capability."""
        return self._capabilities.revoke(agent)

    def enable_capabilities(self, enabled: bool = True) -> None:
        """Enable or disable capability enforcement."""
        self._capabilities.enabled = enabled

    def describe_capabilities(self) -> dict:
        """Return a human-readable description of all capabilities."""
        return self._capabilities.describe()

    # --- Merge Methods ---

    def set_merge_strategy(
        self,
        key: str | None,
        strategy: MergeFunction | str,
    ) -> None:
        """Set a merge strategy for a key or as default.

        When a ConflictError would normally be raised during put(),
        the merge strategy is applied instead — merging the old and
        new values automatically.

        Args:
            key: The key to set strategy for. None sets the default.
            strategy: A merge function or built-in name:
                      "last_write_wins", "list_append", "dict_deep_merge".

        Usage:
            vault.set_merge_strategy("findings", "list_append")
            vault.set_merge_strategy("config", "dict_deep_merge")
            vault.set_merge_strategy("scores", my_custom_merge_fn)
            vault.set_merge_strategy(None, "last_write_wins")  # default
        """
        self._merges.set_strategy(key, strategy)

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

    # --- Causality Methods ---

    def track_causality(self) -> CausalContext:
        """Async context manager to track causal dependencies.

        Within this context, all get() calls record which keys/versions
        were read. When put() is called, these reads are attached as
        causal dependencies in the entry's metadata.

        Usage:
            async with vault.track_causality():
                data = await vault.get("findings")
                await vault.put("summary", summarize(data), agent="writer")
                # summary now has causal_deps={"findings": 3}
        """
        return CausalContext()

    async def causal_chain(
        self, key: str, *, depth: int = 10
    ) -> list[dict[str, Any]]:
        """Trace the full causal chain that led to a key's current value.

        Returns a list of nodes from the target key back to its root causes.
        Each node is a dict with: key, version, agent, causal_deps.

        Args:
            key: The key to trace from.
            depth: Maximum depth to traverse (prevents infinite loops).
        """
        chain: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: list[tuple[str, int]] = []

        # Start with the current entry
        entry = await self.get_entry(key)
        if entry is None:
            return chain

        deps = get_causal_deps(entry)
        chain.append({
            "key": entry.key,
            "version": entry.version,
            "agent": entry.agent,
            "causal_deps": deps,
        })
        visited.add(f"{entry.key}@{entry.version}")

        # Add dependencies to explore
        for dep_key, dep_version in deps.items():
            queue.append((dep_key, dep_version))

        current_depth = 1
        while queue and current_depth < depth:
            next_queue: list[tuple[str, int]] = []
            for dep_key, dep_version in queue:
                visit_id = f"{dep_key}@{dep_version}"
                if visit_id in visited:
                    continue
                visited.add(visit_id)

                # Try to find this specific version in history
                dep_entry = await self._find_version(dep_key, dep_version)
                if dep_entry is None:
                    chain.append({
                        "key": dep_key,
                        "version": dep_version,
                        "agent": None,
                        "causal_deps": {},
                    })
                    continue

                dep_deps = get_causal_deps(dep_entry)
                chain.append({
                    "key": dep_entry.key,
                    "version": dep_entry.version,
                    "agent": dep_entry.agent,
                    "causal_deps": dep_deps,
                })
                for k, v in dep_deps.items():
                    next_queue.append((k, v))

            queue = next_queue
            current_depth += 1

        return chain

    async def is_stale(self, key: str) -> bool:
        """Check if any causal dependency of a key has been updated.

        Returns True if any key that was read to produce this entry
        has since been updated to a newer version.
        """
        entry = await self.get_entry(key)
        if entry is None:
            return False

        deps = get_causal_deps(entry)
        if not deps:
            return False

        for dep_key, dep_version in deps.items():
            dep_entry = await self.get_entry(dep_key)
            if dep_entry is None:
                # Dependency was deleted — definitely stale
                return True
            if dep_entry.version > dep_version:
                return True

        return False

    async def _find_version(self, key: str, version: int) -> Entry | None:
        """Find a specific version of a key in history."""
        entries = await self.history(key)
        for entry in entries:
            if entry.version == version:
                return entry
        return None

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
        # Use active agent if no explicit agent provided
        if agent is None:
            agent = _active_agent.get()

        # Enforce capability-based access control
        self._capabilities.check_write(agent, key)

        # Validate against agent contracts
        self._contracts.validate_put(agent, key, value)

        # Attach causal dependencies if tracking is active
        causal_deps = self._causal.collect_deps()
        if causal_deps:
            if metadata is None:
                metadata = {}
            metadata[CAUSAL_DEPS_KEY] = causal_deps

        value_json, type_hint = serialize(value)

        # Get old value for watch notification
        old_result = await self._backend.get(key)
        old_value = None
        if old_result is not None:
            old_value = deserialize(old_result[0], old_result[1])

        try:
            entry = await self._backend.put(
                key,
                value_json,
                type_hint,
                agent=agent,
                metadata=metadata,
                expected_version=expected_version,
                ttl=ttl,
            )
        except ConflictError:
            # Check if a merge strategy can resolve the conflict
            strategy = self._merges.get_strategy(key)
            if strategy is None or old_value is None:
                raise

            # Apply merge strategy
            merged = strategy(key, old_value, value)
            merged_json, merged_hint = serialize(merged)
            entry = await self._backend.put(
                key,
                merged_json,
                merged_hint,
                agent=agent,
                metadata=metadata,
                ttl=ttl,
                # No expected_version — force write after merge
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
        # Enforce read capability for the active agent
        active = _active_agent.get()
        self._capabilities.check_read(active, key)

        result = await self._backend.get(key)
        if result is None:
            return default
        value_json, type_hint, entry = result
        # Record read for causal tracking
        self._causal.record_read(key, entry.version)
        return deserialize(value_json, type_hint, model=model)

    async def get_entry(self, key: str) -> Entry | None:
        """Retrieve a full Entry (value + metadata) by key.

        Returns None if key is not found.
        """
        # Enforce read capability for the active agent
        active = _active_agent.get()
        self._capabilities.check_read(active, key)

        result = await self._backend.get(key)
        if result is None:
            return None
        entry = result[2]
        # Record read for causal tracking
        self._causal.record_read(key, entry.version)
        return entry

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


class _AsyncAgentContext:
    """Async context manager that sets the active agent."""

    def __init__(self, agent: str) -> None:
        self._agent = agent
        self._token: contextvars.Token[str | None] | None = None

    async def __aenter__(self) -> _AsyncAgentContext:
        self._token = _active_agent.set(self._agent)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._token is not None:
            _active_agent.reset(self._token)
            self._token = None


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
