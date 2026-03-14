"""Typed state with Pydantic models and compare-and-swap."""

from pydantic import BaseModel

from agentvault import ConflictError, Vault


# Define typed state models
class ResearchState(BaseModel):
    papers: list[str]
    summary: str | None = None
    confidence: float = 0.0


class TaskStatus(BaseModel):
    task: str
    status: str  # "pending" | "running" | "complete"
    assigned_to: str | None = None


vault = Vault("typed-demo", backend="memory")

# Store typed state
state = ResearchState(
    papers=["LightRAG", "RAG-Anything"],
    summary="Two RAG frameworks from HKUDS",
    confidence=0.85,
)
vault.put("research", state, agent="researcher")

# Retrieve as typed object
result = vault.get("research", model=ResearchState)
print(f"Type: {type(result).__name__}")
print(f"Papers: {result.papers}")
print(f"Confidence: {result.confidence}")

# Without model= returns a plain dict
raw = vault.get("research")
print(f"\nRaw type: {type(raw).__name__}")
print(f"Raw: {raw}")

# Compare-and-swap for safe concurrent updates
print("\n--- Compare-and-Swap ---")
entry = vault.get_entry("research")
print(f"Current version: {entry.version}")

# Update with version check
updated = ResearchState(
    papers=["LightRAG", "RAG-Anything", "MiniRAG"],
    summary="Three RAG frameworks from HKUDS",
    confidence=0.92,
)
vault.put("research", updated, agent="reviewer", expected_version=entry.version)
print(f"Updated to version: {vault.get_entry('research').version}")

# Conflicting update fails
try:
    vault.put("research", state, agent="intruder", expected_version=1)  # stale version
except ConflictError as e:
    print(f"Conflict detected: {e}")

# Version history
print("\n--- History ---")
for entry in vault.history("research"):
    print(f"  v{entry.version} by {entry.agent}: confidence={entry.value.get('confidence')}")

vault.close()
