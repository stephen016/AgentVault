# AgentVault

**Shared memory and state coordination for AI agents.**

[![PyPI](https://img.shields.io/pypi/v/agentvault)](https://pypi.org/project/agentvault/)
[![Tests](https://img.shields.io/badge/tests-95%20passed-brightgreen)]()
[![Python](https://img.shields.io/pypi/pyversions/agentvault)](https://pypi.org/project/agentvault/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> AgentVault gives multi-agent systems typed, versioned, auditable shared state with coordination primitives — zero infrastructure required.

## The Problem

When multiple AI agents collaborate, they need to share state — research findings, task status, intermediate results. Today, developers hack this together with shared Postgres tables, JSON files, or global dicts. **Mem0** handles *personalization* (remembering user preferences). **AgentVault** handles *coordination* (agents sharing working state in real-time).

## Quickstart

```bash
pip install agentvault
```

```python
from agentvault import Vault

vault = Vault("my-workflow")

# Store state with agent attribution
vault.put("findings", {"papers": ["LightRAG", "GraphRAG"]}, agent="researcher")

# Any agent can read it
print(vault.get("findings"))
# => {"papers": ["LightRAG", "GraphRAG"]}

# Safe concurrent updates via compare-and-swap
vault.put("findings", updated_data, agent="reviewer", expected_version=1)

# Full audit trail
for entry in vault.history("findings"):
    print(f"v{entry.version} by {entry.agent}: {entry.value}")
```

**That's it.** SQLite by default. No servers. No config. `pip install` and go.

## Core Concepts

### Vault

The central shared state store. Create one per workflow or project.

```python
from agentvault import Vault

vault = Vault("my-workflow")              # SQLite (persisted to ~/.agentvault/)
vault = Vault("test", backend="memory")   # In-memory (for testing)
```

### Put / Get / Delete

```python
# get() returns the value directly
vault.put("key", {"any": "json-serializable data"}, agent="my-agent")
value = vault.get("key")                           # -> dict
value = vault.get("missing", default=[])            # -> default if not found

# get_entry() returns full metadata
entry = vault.get_entry("key")
print(entry.key, entry.agent, entry.version, entry.updated_at)

# Delete
vault.delete("key")

# List keys
vault.keys()                                        # -> ["key1", "key2", ...]
vault.keys(agent="researcher")                      # filter by agent
vault.keys(pattern="research_*")                    # glob pattern
```

### Typed State with Pydantic

```python
from pydantic import BaseModel

class ResearchState(BaseModel):
    papers: list[str]
    confidence: float = 0.0

# Store typed state
vault.put("research", ResearchState(papers=["paper1"], confidence=0.9))

# Retrieve as typed object
state = vault.get("research", model=ResearchState)
print(state.papers)      # ["paper1"]
print(state.confidence)  # 0.9
```

### Compare-and-Swap (CAS)

Safe concurrent updates without locks:

```python
from agentvault import ConflictError

entry = vault.get_entry("shared_doc")

try:
    vault.put("shared_doc", new_content,
              agent="editor",
              expected_version=entry.version)  # Only succeeds if version matches
except ConflictError as e:
    print(f"Someone else updated first: expected v{e.expected}, got v{e.actual}")
```

### Distributed Locks

For operations that need exclusive access:

```python
from agentvault.lock import VaultLock

async with VaultLock(vault, "shared-resource", holder="agent-1", timeout=30):
    data = await vault.get("shared-resource")
    await vault.put("shared-resource", transform(data), agent="agent-1")
# Lock auto-released
```

### TTL (Auto-Expiring Entries)

```python
# Scratch work that auto-cleans after 5 minutes
vault.put("temp_results", data, agent="worker", ttl=300)

# After 5 minutes:
vault.get("temp_results")  # -> None (expired)
```

### Watch for Changes

React to state changes in real-time:

```python
# Async iterator — clean, composable, cancellable
async for event in vault.watch("findings"):
    print(f"{event.agent} updated {event.key}: {event.new_value}")

# Watch multiple keys
async for event in vault.watch(["status", "findings"]):
    ...
```

### Agent Context

Auto-tag writes with an agent name:

```python
with vault.as_agent("researcher") as v:
    v.put("notes", "...")        # agent="researcher" implied
    v.put("data", [1, 2, 3])    # agent="researcher" implied
```

### History / Audit Trail

Every change is recorded:

```python
for entry in vault.history("findings"):
    print(f"v{entry.version} by {entry.agent} at {entry.updated_at}")
    print(f"  Value: {entry.value}")
```

## Async API

AgentVault is async-first. The `Vault` class is a sync convenience wrapper.

```python
from agentvault import AsyncVault

async def main():
    vault = await AsyncVault.connect("my-workflow")

    await vault.put("key", "value", agent="agent-1")
    result = await vault.get("key")

    async for event in vault.watch("key"):
        print(event)

    await vault.close()
```

## Backends

| Backend | Best For | Persistence | Dependencies |
|---------|----------|-------------|--------------|
| `sqlite` (default) | Development, single-machine production | Disk (`~/.agentvault/`) | `aiosqlite` |
| `memory` | Testing, ephemeral workflows | None | None |

```python
vault = Vault("my-project")                                    # SQLite default
vault = Vault("my-project", path="/custom/path/vault.db")      # Custom path
vault = Vault("test", backend="memory")                        # In-memory
```

## CLI Inspector

Inspect vault contents from the command line:

```bash
# List all entries
agentvault inspect my-workflow

# Show details for a key
agentvault inspect my-workflow --key findings

# Show version history
agentvault inspect my-workflow --key findings --history

# Filter by agent
agentvault inspect my-workflow --agent researcher
```

Example output:
```
KEY                            AGENT           VERSION  UPDATED                   VALUE PREVIEW
----------------------------------------------------------------------------------------------------
discovered_apis                research-wf     1        2026-03-14 15:30:00       [{"name": "OpenAI", "type": "LLM"...
recommendation                 analysis-wf     1        2026-03-14 15:30:01       {"best_for_prototype": "Ollama"...
research_status                research-wf     2        2026-03-14 15:30:00       "complete"
```

## Integration Examples

AgentVault works with **any** agent framework. See the [`examples/`](examples/) directory:

- [`01_basic_usage.py`](examples/01_basic_usage.py) — Put, get, delete, keys
- [`02_typed_state.py`](examples/02_typed_state.py) — Pydantic models, CAS
- [`03_multi_agent_coordination.py`](examples/03_multi_agent_coordination.py) — Locks, watch, TTL
- [`04_langgraph_integration.py`](examples/04_langgraph_integration.py) — Cross-workflow shared state

## Why AgentVault?

| | AgentVault | Mem0 | Redis | LangGraph State |
|---|---|---|---|---|
| **Purpose** | Agent coordination | Personalization | General KV store | Graph state flow |
| **Typed state** | Pydantic native | No | No | TypedDict |
| **Version history** | Built-in | Partial | No | Checkpoints only |
| **CAS / Locks** | Built-in | No | Manual | No |
| **Framework-agnostic** | Yes | Yes | Yes | LangChain only |
| **Zero config** | SQLite default | Needs vector DB | Needs Redis server | Needs LangChain |
| **TTL** | Built-in | No | Built-in | No |
| **Audit trail** | Built-in | History | No | No |

## Contributing

```bash
git clone https://github.com/agentvault/agentvault.git
cd agentvault
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

## License

MIT
