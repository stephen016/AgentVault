"""Reactive Coordination — dataflow-style pipelines for AI agents."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from agentvault.types import WatchEvent

logger = logging.getLogger(__name__)


@dataclass
class Handler:
    """A registered reactive handler."""

    name: str
    watches: list[str]
    produces: str
    fn: Callable[..., Coroutine[Any, Any, Any]]


class ReactiveEngine:
    """Engine that watches vault keys and dispatches to handler functions.

    Updating one key automatically triggers handler functions that produce
    other keys, enabling dataflow-style reactive pipelines.
    """

    def __init__(self, vault: Any, *, max_depth: int = 10) -> None:
        self._vault = vault
        self._max_depth = max_depth
        self._handlers: list[Handler] = []
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._started_event: asyncio.Event | None = None

    def register(
        self,
        watches: str | list[str],
        produces: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        name: str | None = None,
    ) -> None:
        """Register a handler programmatically."""
        watch_list = [watches] if isinstance(watches, str) else list(watches)

        if produces in watch_list:
            raise ValueError(
                f"Self-loop detected: handler produces '{produces}' "
                f"which is also in its watch list"
            )

        handler_name = name or fn.__name__
        self._handlers.append(Handler(
            name=handler_name,
            watches=watch_list,
            produces=produces,
            fn=fn,
        ))

    def on_update(
        self,
        watches: str | list[str],
        *,
        produces: str,
        name: str | None = None,
    ) -> Callable:
        """Decorator to register a reactive handler."""
        def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable:
            self.register(watches, produces, fn, name=name)
            return fn
        return decorator

    async def start(self) -> None:
        """Launch the background watch loop."""
        if self._running:
            return
        self._running = True
        self._started_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())
        # Wait until the watch loop has registered its queue
        await self._started_event.wait()

    async def stop(self) -> None:
        """Stop the watch loop and await in-flight handlers."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_graph(self) -> dict[str, dict[str, Any]]:
        """Return handler dependency visualization."""
        graph: dict[str, dict[str, Any]] = {}
        for h in self._handlers:
            graph[h.name] = {
                "watches": list(h.watches),
                "produces": h.produces,
            }
        return graph

    def detect_cycles(self) -> list[list[str]]:
        """Find potential infinite loops in the handler graph.

        Returns a list of cycles, where each cycle is a list of key names.
        """
        # Build adjacency: key -> [keys it can trigger via handlers]
        adjacency: dict[str, list[str]] = {}
        for h in self._handlers:
            for w in h.watches:
                adjacency.setdefault(w, []).append(h.produces)

        cycles: list[list[str]] = []
        visited: set[str] = set()

        def dfs(node: str, path: list[str], on_stack: set[str]) -> None:
            if node in on_stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            on_stack.add(node)
            path.append(node)
            for neighbor in adjacency.get(node, []):
                dfs(neighbor, path, on_stack)
            path.pop()
            on_stack.discard(node)

        for key in adjacency:
            if key not in visited:
                dfs(key, [], set())

        return cycles

    async def _run_loop(self) -> None:
        """Main watch loop — dispatches events to matching handlers.

        Directly registers a queue with the vault's watcher list to avoid
        race conditions with async generator setup.
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._vault._watchers.append(queue)

        # Signal that the watch queue is registered and we're ready
        if self._started_event:
            self._started_event.set()

        try:
            while self._running:
                event = await queue.get()
                if event is None:
                    break
                await self._dispatch(event)
        except asyncio.CancelledError:
            pass
        finally:
            if queue in self._vault._watchers:
                self._vault._watchers.remove(queue)

    async def _dispatch(self, event: WatchEvent) -> None:
        """Find handlers whose watches match the event key and run them."""
        if event.event_type != "put":
            return

        depth = getattr(event, "_trigger_depth", 0)
        if depth >= self._max_depth:
            logger.error(
                f"Reactive loop detected on key '{event.key}': "
                f"depth {depth} >= max {self._max_depth}"
            )
            return

        tasks = []
        for handler in self._handlers:
            if event.key in handler.watches:
                tasks.append(
                    asyncio.create_task(
                        self._execute_handler(handler, event, depth)
                    )
                )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_handler(
        self, handler: Handler, event: WatchEvent, depth: int
    ) -> None:
        """Run a single handler and put its result if not None."""
        try:
            # Auto-detect call signature
            sig = inspect.signature(handler.fn)
            params = list(sig.parameters.keys())

            if len(params) >= 1 and params[0] in ("vault_ref", "vault"):
                result = await handler.fn(self._vault, event)
            else:
                result = await handler.fn(event.new_value, event)

            if result is not None:
                await self._vault.put(
                    handler.produces,
                    result,
                    agent=handler.name,
                    _trigger_depth=depth + 1,
                )
        except Exception:
            logger.exception(
                f"Error in reactive handler '{handler.name}' "
                f"triggered by key '{event.key}'"
            )
