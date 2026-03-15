"""Causal Ordering — tracks which data each agent read before writing.

Uses lightweight vector clocks to establish causal relationships between
vault operations. When an agent reads key A (version 3) and then writes
key B, key B's entry records that it causally depends on A@v3.

This enables:
- Tracing the full causal chain that led to any output
- Detecting stale data (a dependency has been updated since it was read)
- Understanding data provenance across multi-agent pipelines
"""

from __future__ import annotations

import contextvars
from typing import Any

# Task-local storage for tracking reads within a causal context.
# Maps key -> version for each read operation.
_causal_reads: contextvars.ContextVar[dict[str, int] | None] = contextvars.ContextVar(
    "_causal_reads", default=None
)

# Metadata key used to store causal dependencies in Entry.metadata
CAUSAL_DEPS_KEY = "_causal_deps"


class CausalTracker:
    """Tracks causal dependencies between vault read and write operations.

    Uses contextvars for async-safe, per-task tracking. When causal tracking
    is active (via track() context manager), every get() records the key and
    version that was read. When put() is called, these recorded reads are
    attached as causal dependencies.
    """

    def record_read(self, key: str, version: int) -> None:
        """Record that a key was read at a specific version."""
        ctx = _causal_reads.get()
        if ctx is not None:
            # Always keep the latest version read for each key
            ctx[key] = max(ctx.get(key, 0), version)

    def collect_deps(self) -> dict[str, int]:
        """Collect accumulated read dependencies without clearing them.

        Returns the current causal deps dict (may be empty).
        Deps are NOT cleared — they persist for the duration of the context.
        """
        ctx = _causal_reads.get()
        if ctx is None:
            return {}
        return dict(ctx)

    def is_tracking(self) -> bool:
        """Return True if causal tracking is currently active."""
        return _causal_reads.get() is not None


class CausalContext:
    """Async context manager for causal tracking.

    Usage:
        async with vault.track_causality():
            data = await vault.get("findings")      # records findings@v3
            await vault.put("summary", summarize(data), agent="writer")
            # summary entry now has causal_deps={"findings": 3}
    """

    def __init__(self) -> None:
        self._token: contextvars.Token[dict[str, int] | None] | None = None

    async def __aenter__(self) -> CausalContext:
        self._token = _causal_reads.set({})
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._token is not None:
            _causal_reads.reset(self._token)
            self._token = None


class SyncCausalContext:
    """Sync context manager for causal tracking."""

    def __init__(self) -> None:
        self._token: contextvars.Token[dict[str, int] | None] | None = None

    def __enter__(self) -> SyncCausalContext:
        self._token = _causal_reads.set({})
        return self

    def __exit__(self, *args: Any) -> None:
        if self._token is not None:
            _causal_reads.reset(self._token)
            self._token = None


def get_causal_deps(entry_or_metadata: Any) -> dict[str, int]:
    """Extract causal dependencies from an Entry or metadata dict."""
    if hasattr(entry_or_metadata, "metadata"):
        metadata = entry_or_metadata.metadata
    else:
        metadata = entry_or_metadata

    return metadata.get(CAUSAL_DEPS_KEY, {})
