"""Example 06: Reactive Pipeline

Demonstrates dataflow-style reactive coordination where updating
one key automatically triggers handler functions that produce other keys.
"""

import asyncio

from agentvault import AsyncVault


async def main():
    print("=" * 60)
    print("  Reactive Pipeline Demo")
    print("=" * 60)
    print()

    vault = await AsyncVault.connect("reactive-demo", backend="memory")

    # --- Register reactive handlers ---

    @vault.on_update("raw_data", produces="cleaned")
    async def clean_data(value, event):
        """Step 1: Clean the raw data."""
        print(f"  [clean_data] Cleaning {len(value)} items...")
        cleaned = [item.strip().lower() for item in value if item.strip()]
        print(f"  [clean_data] -> {len(cleaned)} cleaned items")
        return cleaned

    @vault.on_update("cleaned", produces="analyzed")
    async def analyze(value, event):
        """Step 2: Analyze the cleaned data."""
        print(f"  [analyze] Analyzing {len(value)} items...")
        analysis = {
            "count": len(value),
            "unique": len(set(value)),
            "items": value,
        }
        print(f"  [analyze] -> {analysis['unique']} unique items found")
        return analysis

    @vault.on_update("analyzed", produces="report")
    async def generate_report(value, event):
        """Step 3: Generate a report from the analysis."""
        print(f"  [report] Generating report...")
        report = (
            f"Data Report: {value['count']} items processed, "
            f"{value['unique']} unique entries found. "
            f"Items: {', '.join(value['items'][:5])}"
        )
        print(f"  [report] -> Report complete!")
        return report

    # --- Multi-key join example ---

    @vault.on_update(["report", "metadata"], produces="final_output")
    async def combine(vault_ref, event):
        """Fires when either report or metadata changes; waits for both."""
        report = await vault_ref.get("report")
        meta = await vault_ref.get("metadata")
        if report and meta:
            print(f"  [combine] Both inputs ready, producing final output")
            return {"report": report, "metadata": meta, "status": "complete"}
        return None

    # --- Show the handler graph ---
    engine = vault._ensure_reactive()
    print("Handler Graph:")
    for name, info in engine.get_graph().items():
        print(f"  {name}: watches {info['watches']} -> produces '{info['produces']}'")
    print()

    # --- Check for cycles ---
    cycles = engine.detect_cycles()
    if cycles:
        print(f"WARNING: Cycles detected: {cycles}")
    else:
        print("No cycles detected in handler graph.")
    print()

    # --- Start reactive processing ---
    await vault.start()

    # Trigger the pipeline by writing raw data
    print("Putting raw_data...")
    await vault.put("raw_data", [
        "  LightRAG  ", "GraphRAG", "lightrag", "  HippoRAG ", "GraphRAG"
    ], agent="ingester")

    # Wait for the chain to complete
    await asyncio.sleep(0.5)

    # Check intermediate results
    print()
    print("--- Results ---")
    print(f"cleaned: {await vault.get('cleaned')}")
    print(f"analyzed: {await vault.get('analyzed')}")
    print(f"report: {await vault.get('report')}")
    print(f"final_output: {await vault.get('final_output')}")
    print()

    # Now add metadata to trigger the join
    print("Putting metadata...")
    await vault.put("metadata", {"source": "arxiv", "date": "2026-03-14"}, agent="admin")
    await asyncio.sleep(0.3)

    print(f"final_output: {await vault.get('final_output')}")
    print()

    await vault.stop()
    await vault.close()

    print("=" * 60)
    print("  Pipeline Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
