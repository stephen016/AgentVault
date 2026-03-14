"""Distributed lock implementation for AgentVault."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from agentvault.exceptions import ConflictError, LockError


class VaultLock:
    """A distributed lock backed by a vault entry.

    Uses a special `__lock:{key}` entry with holder ID and expiry timestamp.
    Acquisition uses CAS (create-if-absent, check-expiry-if-exists).

    Usage (async):
        async with vault.lock("my-key", holder="agent-1"):
            data = await vault.get("my-key")
            await vault.put("my-key", transform(data))

    Usage (sync):
        with vault.lock("my-key", holder="agent-1"):
            data = vault.get("my-key")
            vault.put("my-key", transform(data))
    """

    def __init__(
        self,
        vault: Any,  # AsyncVault — avoid circular import
        key: str,
        holder: str,
        timeout: float = 30.0,
        poll_interval: float = 0.1,
    ) -> None:
        self._vault = vault
        self._lock_key = f"__lock:{key}"
        self._holder = holder
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._lock_id = str(uuid.uuid4())

    async def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if successful.

        Raises LockError if the lock cannot be acquired within the timeout.
        """
        deadline = datetime.now(timezone.utc) + timedelta(seconds=self._timeout)

        while datetime.now(timezone.utc) < deadline:
            # Check if lock exists
            result = await self._vault._backend.get(self._lock_key)

            if result is None:
                # No lock — try to create it via CAS (expected_version=0)
                try:
                    expires_at = datetime.now(timezone.utc) + timedelta(
                        seconds=self._timeout
                    )
                    lock_data = {
                        "holder": self._holder,
                        "lock_id": self._lock_id,
                        "expires_at": expires_at.isoformat(),
                    }
                    await self._vault._backend.put(
                        self._lock_key,
                        json.dumps(lock_data),
                        None,
                        agent=self._holder,
                        expected_version=0,
                    )
                    return True
                except ConflictError:
                    # Someone else grabbed it between our check and create
                    await asyncio.sleep(self._poll_interval)
                    continue

            # Lock exists — check if expired
            lock_data = json.loads(result[0])
            expires_at = datetime.fromisoformat(lock_data["expires_at"])

            if datetime.now(timezone.utc) >= expires_at:
                # Lock expired — try to take it over via CAS
                try:
                    new_expires = datetime.now(timezone.utc) + timedelta(
                        seconds=self._timeout
                    )
                    new_lock_data = {
                        "holder": self._holder,
                        "lock_id": self._lock_id,
                        "expires_at": new_expires.isoformat(),
                    }
                    await self._vault._backend.put(
                        self._lock_key,
                        json.dumps(new_lock_data),
                        None,
                        agent=self._holder,
                        expected_version=result[2].version,
                    )
                    return True
                except ConflictError:
                    # Someone else took over the expired lock
                    await asyncio.sleep(self._poll_interval)
                    continue

            # Lock held by someone else — wait
            await asyncio.sleep(self._poll_interval)

        raise LockError(self._lock_key, self._holder)

    async def release(self) -> None:
        """Release the lock. Only releases if we hold it."""
        result = await self._vault._backend.get(self._lock_key)
        if result is not None:
            lock_data = json.loads(result[0])
            if lock_data.get("lock_id") == self._lock_id:
                await self._vault._backend.delete(self._lock_key)

    async def __aenter__(self) -> VaultLock:
        await self.acquire()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.release()
