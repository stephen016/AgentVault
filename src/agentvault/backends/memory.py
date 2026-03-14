"""In-memory backend for AgentVault. Used for testing and lightweight use cases."""

from __future__ import annotations

import fnmatch
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from agentvault.backends.base import Backend
from agentvault.exceptions import ConflictError
from agentvault.types import Entry


class MemoryBackend(Backend):
    """Dict-based in-memory backend. Zero dependencies, no persistence."""

    def __init__(self) -> None:
        # key -> (json_str, type_hint, Entry)
        self._store: dict[str, tuple[str, str | None, Entry]] = {}
        # key -> list of Entry (version history)
        self._history: dict[str, list[Entry]] = {}

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
        now = datetime.now(timezone.utc)
        existing = self._store.get(key)

        if existing is not None:
            current_version = existing[2].version
            if expected_version is not None and current_version != expected_version:
                raise ConflictError(key, expected_version, current_version)
            new_version = current_version + 1
            created_at = existing[2].created_at
        else:
            if expected_version is not None and expected_version != 0:
                raise ConflictError(key, expected_version, 0)
            new_version = 1
            created_at = now

        # Compute expires_at
        expires_at: datetime | None = None
        if ttl is not None:
            from datetime import timedelta

            expires_at = now + timedelta(seconds=ttl)

        value = json.loads(value_json)
        entry_metadata = dict(metadata or {})
        if type_hint is not None:
            entry_metadata["_type_hint"] = type_hint
        if expires_at is not None:
            entry_metadata["_expires_at"] = expires_at.isoformat()

        entry = Entry(
            key=key,
            value=value,
            agent=agent,
            version=new_version,
            created_at=created_at,
            updated_at=now,
            metadata=entry_metadata,
        )

        self._store[key] = (value_json, type_hint, entry)

        # Append to history
        if key not in self._history:
            self._history[key] = []
        self._history[key].append(deepcopy(entry))

        return entry

    async def get(self, key: str) -> tuple[str, str | None, Entry] | None:
        result = self._store.get(key)
        if result is None:
            return None

        # Check TTL
        entry = result[2]
        expires_at_str = entry.metadata.get("_expires_at")
        if expires_at_str is not None:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) >= expires_at:
                del self._store[key]
                return None

        return result

    async def delete(self, key: str) -> bool:
        if key not in self._store:
            return False

        entry = self._store[key][2]
        now = datetime.now(timezone.utc)

        # Record deletion in history
        delete_entry = Entry(
            key=key,
            value=None,
            agent=entry.agent,
            version=entry.version + 1,
            created_at=entry.created_at,
            updated_at=now,
            metadata={"_operation": "delete"},
        )
        if key not in self._history:
            self._history[key] = []
        self._history[key].append(delete_entry)

        del self._store[key]
        return True

    async def keys(
        self,
        *,
        pattern: str | None = None,
        agent: str | None = None,
    ) -> list[str]:
        result = []
        for key, (_, _, entry) in self._store.items():
            # Check TTL
            expires_at_str = entry.metadata.get("_expires_at")
            if expires_at_str is not None:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(timezone.utc) >= expires_at:
                    continue

            if pattern is not None and not fnmatch.fnmatch(key, pattern):
                continue
            if agent is not None and entry.agent != agent:
                continue
            result.append(key)
        return sorted(result)

    async def history(self, key: str, *, limit: int = 100) -> list[Entry]:
        entries = self._history.get(key, [])
        # Return newest first, limited
        return list(reversed(entries[-limit:]))

    async def clear(self) -> int:
        count = len(self._store)
        self._store.clear()
        self._history.clear()
        return count
