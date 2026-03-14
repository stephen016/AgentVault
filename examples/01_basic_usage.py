"""Basic AgentVault usage — put, get, delete, keys."""

from agentvault import Vault

# Create a vault (SQLite by default, stored at ~/.agentvault/demo.db)
vault = Vault("demo", backend="memory")  # Use "memory" for this demo

# Store values with agent attribution
vault.put("research_findings", {
    "papers": ["Attention Is All You Need", "BERT", "GPT-4"],
    "status": "complete",
}, agent="researcher")

vault.put("summary", "Three landmark papers on transformer architectures.", agent="writer")

# Retrieve values
findings = vault.get("research_findings")
print(f"Findings: {findings}")

# Get with default for missing keys
missing = vault.get("nonexistent", default="not found")
print(f"Missing key: {missing}")

# Get full entry with metadata
entry = vault.get_entry("research_findings")
print(f"\nEntry details:")
print(f"  Key:     {entry.key}")
print(f"  Agent:   {entry.agent}")
print(f"  Version: {entry.version}")
print(f"  Updated: {entry.updated_at}")

# List all keys
print(f"\nAll keys: {vault.keys()}")
print(f"Keys by researcher: {vault.keys(agent='researcher')}")
print(f"Keys matching 'res*': {vault.keys(pattern='res*')}")

# Delete
vault.delete("summary")
print(f"\nAfter delete: {vault.keys()}")

# Context manager usage
with Vault("demo2", backend="memory") as v:
    v.put("temp", "data")
    print(f"\nContext manager: {v.get('temp')}")

vault.close()
print("\nDone!")
