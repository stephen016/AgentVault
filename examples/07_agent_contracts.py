"""Example 07: Agent Contracts

Demonstrates typed declarations of what each agent produces and consumes,
validated at runtime. Makes coordination self-documenting and error-proof.
"""

from agentvault import AgentContract, ContractViolationError, Vault


def main():
    print("=" * 60)
    print("  Agent Contracts Demo")
    print("=" * 60)
    print()

    with Vault("contracts-demo", backend="memory") as vault:
        # --- Register agent contracts ---

        vault.register_agent(AgentContract(
            name="researcher",
            produces={"findings": dict, "scratch": str},
            consumes={"plan": str},
            description="Researches topics and produces findings",
        ))

        vault.register_agent(AgentContract(
            name="writer",
            produces={"report": str},
            consumes={"findings": dict},
            description="Writes reports from research findings",
        ))

        vault.register_agent(AgentContract(
            name="planner",
            produces={"plan": str},
            consumes={},
            description="Creates research plans",
        ))

        # --- Show dependency graph ---

        print("Dependency Graph:")
        graph = vault.get_dependency_graph()
        for agent_name, info in graph.items():
            produces = ", ".join(info["produces"].keys()) or "(none)"
            consumes = ", ".join(info["consumes"].keys()) or "(none)"
            desc = info.get("description", "")
            print(f"  {agent_name}: produces [{produces}], consumes [{consumes}]")
            if desc:
                print(f"    -> {desc}")
        print()

        # --- Validate contracts structurally ---

        issues = vault.validate_contracts()
        if issues:
            print("Structural Issues:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("No structural issues found.")
        print()

        # --- Enforcement off (default) ---

        print("--- Enforcement: off (default) ---")
        vault.put("anything", "no restrictions", agent="researcher")
        print("  researcher wrote to 'anything' -> OK (no enforcement)")
        print()

        # --- Enforcement: warn ---

        print("--- Enforcement: warn ---")
        vault.set_enforcement("warn")
        vault.put("wrong_key", "data", agent="researcher")
        print("  researcher wrote to 'wrong_key' -> logged warning, but succeeded")
        print()

        # --- Enforcement: strict ---

        print("--- Enforcement: strict ---")
        vault.set_enforcement("strict")

        # Valid operations
        with vault.as_agent("planner") as v:
            v.put("plan", "Research RAG architectures")
            print("  planner wrote 'plan' -> OK")

        with vault.as_agent("researcher") as v:
            v.put("findings", {"papers": ["LightRAG", "GraphRAG"]})
            print("  researcher wrote 'findings' (dict) -> OK")

            v.put("scratch", "temporary notes")
            print("  researcher wrote 'scratch' (str) -> OK")

        with vault.as_agent("writer") as v:
            v.put("report", "Final research report on RAG architectures")
            print("  writer wrote 'report' (str) -> OK")

        print()

        # Violations
        print("--- Violations (strict mode) ---")

        # Wrong key
        try:
            with vault.as_agent("writer") as v:
                v.put("findings", {"data": "unauthorized"})
        except ContractViolationError as e:
            print(f"  BLOCKED: {e}")

        # Wrong type
        try:
            with vault.as_agent("writer") as v:
                v.put("report", 42)  # expects str, got int
        except ContractViolationError as e:
            print(f"  BLOCKED: {e}")

        print()
        print("--- Final State ---")
        for key in vault.keys():
            entry = vault.get_entry(key)
            if entry:
                preview = str(entry.value)[:50]
                print(f"  {key} (v{entry.version}, agent={entry.agent}): {preview}")

    print()
    print("=" * 60)
    print("  Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
