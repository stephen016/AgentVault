"""Example: Using AgentVault alongside LangGraph for cross-workflow shared state.

This example shows how AgentVault can provide shared memory between
multiple LangGraph workflows or between LangGraph and non-LangGraph agents.

Note: This is a conceptual example. Install langgraph to run it fully.
"""

from agentvault import Vault


def simulate_langgraph_workflow() -> None:
    """Simulates how you'd use AgentVault with LangGraph."""

    # Shared vault accessible by all workflows
    vault = Vault("project-alpha", backend="memory")

    # --- Workflow 1: Research Agent ---
    print("=== Workflow 1: Research ===")
    with vault.as_agent("research-workflow") as v:
        v.put("research_status", "running")
        v.put("discovered_apis", [
            {"name": "OpenAI", "type": "LLM", "cost": "high"},
            {"name": "Anthropic", "type": "LLM", "cost": "medium"},
            {"name": "Ollama", "type": "local", "cost": "free"},
        ])
        v.put("research_status", "complete")
    print(f"  Status: {vault.get('research_status')}")
    print(f"  APIs found: {len(vault.get('discovered_apis'))}")

    # --- Workflow 2: Analysis Agent (reads research, writes analysis) ---
    print("\n=== Workflow 2: Analysis ===")
    with vault.as_agent("analysis-workflow") as v:
        # Read what the research workflow found
        apis = v.get("discovered_apis")

        # Analyze and write results
        free_apis = [a for a in apis if a["cost"] == "free"]
        v.put("recommendation", {
            "best_for_prototype": free_apis[0]["name"] if free_apis else "none",
            "best_for_production": "Anthropic",
            "reasoning": "Ollama for dev, Anthropic for quality",
        })
    print(f"  Recommendation: {vault.get('recommendation')}")

    # --- Workflow 3: Report Agent (reads everything, generates report) ---
    print("\n=== Workflow 3: Report ===")
    with vault.as_agent("report-workflow") as v:
        apis = v.get("discovered_apis")
        rec = v.get("recommendation")
        report = (
            f"Found {len(apis)} APIs. "
            f"Recommend {rec['best_for_prototype']} for prototyping, "
            f"{rec['best_for_production']} for production."
        )
        v.put("final_report", report)
    print(f"  Report: {vault.get('final_report')}")

    # --- Cross-workflow audit trail ---
    print("\n=== Audit Trail ===")
    for key in vault.keys():
        entry = vault.get_entry(key)
        print(f"  {key:<25} v{entry.version}  by {entry.agent}")

    print("\n=== All agents that contributed ===")
    agents = set()
    for key in vault.keys():
        entry = vault.get_entry(key)
        if entry and entry.agent:
            agents.add(entry.agent)
    for agent in sorted(agents):
        agent_keys = vault.keys(agent=agent)
        print(f"  {agent}: {agent_keys}")

    vault.close()


if __name__ == "__main__":
    simulate_langgraph_workflow()
