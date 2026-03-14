<h1 align="center">AgentVault</h1>

<p align="center">
  <strong>Shared memory and state coordination for AI agents.</strong>
</p>

<p align="center">
  <a href="https://github.com/stephen016/AgentVault/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/tests-100%20passed-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/dependencies-2-green" alt="Dependencies">
</p>

<p align="center">
  <em>Typed, versioned, auditable shared state with coordination primitives — zero infrastructure required.</em>
</p>

---

## Demo: 3 Agents Collaborating via AgentVault

```
============================================================
  Multi-Agent Research Pipeline with AgentVault
============================================================

[planner] Defining research plan...
[researcher] Waiting for research plan...
[writer] Waiting for research to complete...
[planner] Plan ready: 3 questions to research
  [+] plan v1 <- planner
  [+] pipeline_status v1 <- planner
[researcher] Got plan: 'The Rise of RAG' with 3 questions
  [+] findings v1 <- researcher
[researcher] Found answer 1/3: confidence=92%
  [+] findings v2 <- researcher
[researcher] Found answer 2/3: confidence=95%
  [+] findings v3 <- researcher
[researcher] Found answer 3/3: confidence=88%
[researcher] All research complete!
  [+] pipeline_status v2 <- researcher
[writer] Got 3 findings, writing report...
[writer] Report complete: 100 words, 3 sections
  [+] report v1 <- writer

============================================================
  Pipeline Complete! (1.4s)
============================================================

--- Audit Trail: findings ---
  v4 by researcher: 3 findings, status=complete
  v3 by researcher: 2 findings, status=in_progress
  v2 by researcher: 1 findings, status=in_progress
  v1 by researcher: 0 findings, status=in_progress
```

> Run it yourself: `python examples/05_real_world_research_team.py`

---

## The Problem

When multiple AI agents collaborate, they need to share state — research findings, task status, intermediate results. Today, developers hack this with shared dicts, JSON files, or raw databases.

**Mem0** handles *personalization* (remembering user preferences). **AgentVault** handles *coordination* (agents sharing working state in real-time).

## Install

```bash
pip install agentvault
```

Two dependencies: `pydantic` + `aiosqlite`. That's it.

## Quickstart (30 seconds)

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

**SQLite by default. No servers. No config.** `pip install` and go.

## Features at a Glance

| Feature | Example |
|---------|---------|
| **Put / Get / Delete** | `vault.put("key", value, agent="name")` |
| **Typed state** | `vault.get("key", model=MyPydanticModel)` |
| **Compare-and-swap** | `vault.put("key", val, expected_version=3)` |
| **Distributed locks** | `with vault.lock("key", holder="agent"):` |
| **TTL auto-expiry** | `vault.put("temp", data, ttl=300)` |
| **Watch changes** | `async for event in vault.watch("key"):` |
| **Agent context** | `with vault.as_agent("researcher") as v:` |
| **Audit trail** | `vault.history("key")` |
| **CLI inspector** | `agentvault inspect my-workflow` |

---

## Core API

### Put / Get / Delete

```python
vault.put("key", {"any": "json data"}, agent="my-agent")
value = vault.get("key")                           # -> dict
value = vault.get("missing", default=[])            # -> default if not found

entry = vault.get_entry("key")                      # -> Entry with .version, .agent, etc.

vault.delete("key")
vault.keys()                                        # -> ["key1", "key2"]
vault.keys(agent="researcher")                      # filter by agent
vault.keys(pattern="research_*")                    # glob pattern
```

### Typed State with Pydantic

```python
from pydantic import BaseModel

class ResearchState(BaseModel):
    papers: list[str]
    confidence: float = 0.0

vault.put("research", ResearchState(papers=["paper1"], confidence=0.9))
state = vault.get("research", model=ResearchState)  # -> ResearchState object
```

### Compare-and-Swap (CAS)

```python
entry = vault.get_entry("shared_doc")
try:
    vault.put("shared_doc", new_content, agent="editor",
              expected_version=entry.version)
except ConflictError as e:
    print(f"Conflict: expected v{e.expected}, got v{e.actual}")
```

### Distributed Locks

```python
# Sync
with vault.lock("resource", holder="agent-1", timeout=30):
    data = vault.get("resource")
    vault.put("resource", transform(data), agent="agent-1")

# Async
async with VaultLock(vault, "resource", holder="agent-1"):
    ...
```

### TTL (Auto-Expiring Entries)

```python
vault.put("scratch_work", data, agent="worker", ttl=300)  # expires in 5 min
# After 5 min: vault.get("scratch_work") -> None
```

### Watch for Changes

```python
async for event in vault.watch("findings"):
    print(f"{event.agent} updated {event.key}: {event.new_value}")

async for event in vault.watch(["status", "findings"]):  # multiple keys
    ...
```

### Agent Context

```python
with vault.as_agent("researcher") as v:
    v.put("notes", "...")        # agent="researcher" auto-tagged
    v.put("data", [1, 2, 3])    # agent="researcher" auto-tagged
```

### Audit Trail

```python
for entry in vault.history("findings"):
    print(f"v{entry.version} by {entry.agent} at {entry.updated_at}")
```

## Async API

AgentVault is async-first. The `Vault` class is a sync convenience wrapper.

```python
from agentvault import AsyncVault

vault = await AsyncVault.connect("my-workflow")
await vault.put("key", "value", agent="agent-1")
result = await vault.get("key")
await vault.close()
```

## CLI Inspector

```bash
agentvault inspect my-workflow                          # list all entries
agentvault inspect my-workflow --key findings           # show key details
agentvault inspect my-workflow --key findings --history # version history
agentvault inspect my-workflow --agent researcher       # filter by agent
agentvault inspect my-workflow --watch                  # live monitoring
```

```
KEY                            AGENT           VERSION  UPDATED                   VALUE PREVIEW
----------------------------------------------------------------------------------------------------
findings                       researcher      4        2026-03-14 15:34:48       {"papers": ["LightRAG", "GraphRAG"...
pipeline_status                writer          3        2026-03-14 15:34:49       "report_complete"
plan                           planner         1        2026-03-14 15:34:48       {"topic": "The Rise of Retrieval-A...
report                         writer          1        2026-03-14 15:34:49       {"title": "Research Report: The Ri...
```

## Backends

| Backend | Best For | Persistence | Config |
|---------|----------|-------------|--------|
| `sqlite` (default) | Dev + single-machine prod | `~/.agentvault/` | Zero config |
| `memory` | Testing | None | `backend="memory"` |

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

## Examples

| Example | What it shows |
|---------|--------------|
| [`01_basic_usage.py`](examples/01_basic_usage.py) | Put, get, delete, keys |
| [`02_typed_state.py`](examples/02_typed_state.py) | Pydantic models, CAS |
| [`03_multi_agent_coordination.py`](examples/03_multi_agent_coordination.py) | Locks, watch, TTL |
| [`04_langgraph_integration.py`](examples/04_langgraph_integration.py) | Cross-workflow shared state |
| [`05_real_world_research_team.py`](examples/05_real_world_research_team.py) | **Full multi-agent pipeline** |

## Contributing

```bash
git clone https://github.com/stephen016/AgentVault.git
cd AgentVault
pip install -e ".[dev]"
pytest                    # 100 tests
ruff check src/ tests/    # linting
```

## License

MIT
