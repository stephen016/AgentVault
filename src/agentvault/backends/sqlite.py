"""SQLite backend for AgentVault. The default backend — zero config, works everywhere."""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from agentvault.backends.base import Backend
from agentvault.exceptions import ConflictError
from agentvault.types import Entry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    type_hint TEXT,
    agent TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS entry_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    type_hint TEXT,
    agent TEXT,
    version INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT 'put',
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_history_key ON entry_history(key);
CREATE INDEX IF NOT EXISTS idx_entries_agent ON entries(agent);
"""


class SQLiteBackend(Backend):
    """SQLite-based persistent backend using aiosqlite."""

    def __init__(self, vault_name: str = "default", path: str | None = None) -> None:
        if path is not None:
            self._db_path = path
        else:
            db_dir = Path.home() / ".agentvault"
            db_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = str(db_dir / f"{vault_name}.db")
        self._db: aiosqlite.Connection | None = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.executescript(_SCHEMA)
            await self._db.commit()
        return self._db

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
        db = await self._ensure_db()
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        meta = dict(metadata or {})
        if type_hint is not None:
            meta["_type_hint"] = type_hint
        meta_json = json.dumps(meta)

        expires_at_str: str | None = None
        if ttl is not None:
            expires_at_str = (now + timedelta(seconds=ttl)).isoformat()

        # Check existing entry
        cursor = await db.execute("SELECT version, created_at FROM entries WHERE key = ?", (key,))
        row = await cursor.fetchone()

        if row is not None:
            current_version = row["version"]
            created_at_str = row["created_at"]
            if expected_version is not None and current_version != expected_version:
                raise ConflictError(key, expected_version, current_version)
            new_version = current_version + 1

            await db.execute(
                """UPDATE entries
                   SET value_json = ?, type_hint = ?, agent = ?, version = ?,
                       updated_at = ?, expires_at = ?, metadata = ?
                   WHERE key = ?""",
                (value_json, type_hint, agent, new_version,
                 now_str, expires_at_str, meta_json, key),
            )
        else:
            if expected_version is not None and expected_version != 0:
                raise ConflictError(key, expected_version, 0)
            new_version = 1
            created_at_str = now_str

            await db.execute(
                """INSERT INTO entries (key, value_json, type_hint, agent, version,
                                       created_at, updated_at, expires_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, value_json, type_hint, agent, new_version,
                 created_at_str, now_str, expires_at_str, meta_json),
            )

        # Record in history
        await db.execute(
            """INSERT INTO entry_history (key, value_json, type_hint, agent, version,
                                         timestamp, operation, metadata)
               VALUES (?, ?, ?, ?, ?, ?, 'put', ?)""",
            (key, value_json, type_hint, agent, new_version, now_str, meta_json),
        )

        await db.commit()

        value = json.loads(value_json)
        return Entry(
            key=key,
            value=value,
            agent=agent,
            version=new_version,
            created_at=datetime.fromisoformat(created_at_str),
            updated_at=now,
            metadata=meta,
        )

    async def get(self, key: str) -> tuple[str, str | None, Entry] | None:
        db = await self._ensure_db()
        cursor = await db.execute(
            "SELECT * FROM entries WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        # Check TTL
        if row["expires_at"] is not None:
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) >= expires_at:
                await db.execute("DELETE FROM entries WHERE key = ?", (key,))
                await db.commit()
                return None

        meta = json.loads(row["metadata"])
        value = json.loads(row["value_json"])
        entry = Entry(
            key=row["key"],
            value=value,
            agent=row["agent"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=meta,
        )
        return (row["value_json"], row["type_hint"], entry)

    async def delete(self, key: str) -> bool:
        db = await self._ensure_db()
        cursor = await db.execute("SELECT version, agent FROM entries WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row is None:
            return False

        now_str = datetime.now(timezone.utc).isoformat()

        # Record deletion in history
        await db.execute(
            """INSERT INTO entry_history (key, value_json, type_hint, agent, version,
                                         timestamp, operation, metadata)
               VALUES (?, 'null', NULL, ?, ?, ?, 'delete', '{}')""",
            (key, row["agent"], row["version"] + 1, now_str),
        )

        await db.execute("DELETE FROM entries WHERE key = ?", (key,))
        await db.commit()
        return True

    async def keys(
        self,
        *,
        pattern: str | None = None,
        agent: str | None = None,
    ) -> list[str]:
        db = await self._ensure_db()
        now_str = datetime.now(timezone.utc).isoformat()

        query = "SELECT key, agent FROM entries WHERE (expires_at IS NULL OR expires_at > ?)"
        params: list[Any] = [now_str]

        if agent is not None:
            query += " AND agent = ?"
            params.append(agent)

        query += " ORDER BY key"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        if pattern is not None:
            return [row["key"] for row in rows if fnmatch.fnmatch(row["key"], pattern)]
        return [row["key"] for row in rows]

    async def history(self, key: str, *, limit: int = 100) -> list[Entry]:
        db = await self._ensure_db()
        cursor = await db.execute(
            """SELECT * FROM entry_history
               WHERE key = ?
               ORDER BY version DESC
               LIMIT ?""",
            (key, limit),
        )
        rows = await cursor.fetchall()

        entries = []
        for row in rows:
            value = json.loads(row["value_json"])
            meta = json.loads(row["metadata"])
            entries.append(Entry(
                key=row["key"],
                value=value,
                agent=row["agent"],
                version=row["version"],
                created_at=datetime.fromisoformat(row["timestamp"]),
                updated_at=datetime.fromisoformat(row["timestamp"]),
                metadata=meta,
            ))
        return entries

    async def clear(self) -> int:
        db = await self._ensure_db()
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM entries")
        row = await cursor.fetchone()
        count = row["cnt"] if row else 0

        await db.execute("DELETE FROM entries")
        await db.execute("DELETE FROM entry_history")
        await db.commit()
        return count

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
