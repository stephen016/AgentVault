"""Multi-agent coordination with locks, watch, and TTL."""

import asyncio

from agentvault import AsyncVault, WatchEvent
from agentvault.lock import VaultLock


async def researcher(vault: AsyncVault) -> None:
    """Simulates a research agent that discovers papers."""
    print("[researcher] Starting research...")
    await asyncio.sleep(0.1)

    await vault.put("findings", {
        "papers": ["LightRAG", "GraphRAG"],
        "count": 2,
    }, agent="researcher")
    print("[researcher] Published findings (2 papers)")

    await asyncio.sleep(0.3)

    # Use lock for safe update
    async with VaultLock(vault, "findings", holder="researcher"):
        current = await vault.get("findings")
        current["papers"].append("RAG-Anything")
        current["count"] = 3
        await vault.put("findings", current, agent="researcher")
    print("[researcher] Updated findings (3 papers)")

    # Store temporary scratch work with TTL
    await vault.put("scratch_notes", "raw web results...", agent="researcher", ttl=2)
    print("[researcher] Stored scratch notes (expires in 2s)")


async def summarizer(vault: AsyncVault) -> None:
    """Simulates a summarizer agent that watches for findings."""
    print("[summarizer] Waiting for findings...")

    async for event in vault.watch("findings"):
        papers = event.new_value.get("papers", [])
        print(f"[summarizer] Got update: {len(papers)} papers from {event.agent}")

        if len(papers) >= 3:
            # Use lock to safely write summary
            async with VaultLock(vault, "summary", holder="summarizer"):
                await vault.put("summary", {
                    "text": f"Found {len(papers)} papers: {', '.join(papers)}",
                    "based_on_version": event.version,
                }, agent="summarizer")
            print("[summarizer] Published summary")
            break


async def monitor(vault: AsyncVault) -> None:
    """Monitors all vault changes."""
    count = 0
    async for event in vault.watch():
        icon = "+" if event.event_type == "put" else "-"
        print(f"  [{icon}] {event.key} v{event.version} by {event.agent}")
        count += 1
        if count >= 4:
            break


async def main() -> None:
    vault = await AsyncVault.connect("coordination-demo", backend="memory")

    print("=== Multi-Agent Coordination Demo ===\n")

    # Run agents concurrently
    await asyncio.gather(
        researcher(vault),
        summarizer(vault),
        monitor(vault),
    )

    # Check results
    print("\n=== Final State ===")
    for key in await vault.keys():
        entry = await vault.get_entry(key)
        if entry:
            print(f"  {key} (v{entry.version}, by {entry.agent}): {entry.value}")

    # Check scratch notes expired
    await asyncio.sleep(2.1)
    scratch = await vault.get("scratch_notes")
    print(f"\n  scratch_notes after TTL: {scratch}")

    # Show history
    print("\n=== History for 'findings' ===")
    for entry in await vault.history("findings"):
        print(f"  v{entry.version} by {entry.agent}: {entry.value}")

    await vault.close()


if __name__ == "__main__":
    asyncio.run(main())
