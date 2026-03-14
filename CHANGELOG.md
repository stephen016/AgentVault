# Changelog

## v0.1.0 (2026-03-14)

Initial release.

### Features

- **Vault** (sync) and **AsyncVault** (async) shared state stores
- **SQLite backend** — zero-config persistent storage with WAL mode
- **Memory backend** — in-memory for testing
- **Pydantic support** — store and retrieve typed models
- **Compare-and-swap** — `expected_version` for safe concurrent updates
- **Distributed locks** — `VaultLock` with timeout and holder tracking
- **TTL** — auto-expiring entries with lazy deletion
- **Watch** — async iterator for real-time change notifications
- **Agent context** — `as_agent()` context manager for auto-tagging
- **Version history** — full audit trail for every key
- **CLI inspector** — `agentvault inspect` command
- **Key filtering** — by glob pattern or agent name
