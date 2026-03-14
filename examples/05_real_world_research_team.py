"""Real-world demo: 3 AI agents collaborating on a research task.

This demo simulates a realistic multi-agent research pipeline:
  1. Planner agent defines the research plan
  2. Researcher agent gathers information
  3. Writer agent synthesizes a final report

All agents coordinate through AgentVault — sharing state, watching for
updates, and using locks for safe concurrent access.

Run: python examples/05_real_world_research_team.py
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from pydantic import BaseModel

from agentvault import AsyncVault, WatchEvent
from agentvault.lock import VaultLock


# ── Typed State Models ────────────────────────────────────────

class ResearchPlan(BaseModel):
    topic: str
    questions: list[str]
    deadline: str


class Finding(BaseModel):
    question: str
    answer: str
    sources: list[str]
    confidence: float


class ResearchFindings(BaseModel):
    findings: list[Finding]
    status: str  # "in_progress" | "complete"


class Report(BaseModel):
    title: str
    sections: list[dict[str, str]]
    word_count: int
    generated_at: str


# ── Agent Implementations ────────────────────────────────────

async def planner_agent(vault: AsyncVault) -> None:
    """Plans the research by defining questions to investigate."""
    print("\n[planner] Defining research plan...")
    await asyncio.sleep(0.2)  # Simulate thinking

    plan = ResearchPlan(
        topic="The Rise of Retrieval-Augmented Generation (RAG)",
        questions=[
            "What are the key RAG architectures in 2025-2026?",
            "How does LightRAG differ from traditional RAG?",
            "What are the main challenges in production RAG systems?",
        ],
        deadline="2026-03-20",
    )

    await vault.put("plan", plan, agent="planner")
    await vault.put("pipeline_status", "planning_complete", agent="planner")
    print(f"[planner] Plan ready: {len(plan.questions)} questions to research")


async def researcher_agent(vault: AsyncVault) -> None:
    """Gathers findings based on the research plan."""
    # Wait for the plan
    print("[researcher] Waiting for research plan...")
    async for event in vault.watch("pipeline_status"):
        if event.new_value == "planning_complete":
            break

    plan = await vault.get("plan", model=ResearchPlan)
    print(f"[researcher] Got plan: '{plan.topic}' with {len(plan.questions)} questions")

    # Initialize findings
    findings = ResearchFindings(findings=[], status="in_progress")
    await vault.put("findings", findings, agent="researcher")

    # Research each question (simulated)
    simulated_answers = [
        Finding(
            question=plan.questions[0],
            answer=(
                "Key RAG architectures include vanilla RAG (retrieve-then-generate), "
                "LightRAG (graph-enhanced retrieval), RAG-Anything (multimodal), "
                "and GraphRAG (Microsoft's knowledge graph approach)."
            ),
            sources=["arxiv:2410.05779", "arxiv:2404.16130"],
            confidence=0.92,
        ),
        Finding(
            question=plan.questions[1],
            answer=(
                "LightRAG introduces dual-level retrieval combining vector similarity "
                "with knowledge graph traversal. It automatically extracts entities and "
                "relationships, enabling deeper semantic understanding compared to "
                "traditional chunk-based RAG."
            ),
            sources=["arxiv:2410.05779", "github.com/HKUDS/LightRAG"],
            confidence=0.95,
        ),
        Finding(
            question=plan.questions[2],
            answer=(
                "Main challenges: (1) context window limitations with large documents, "
                "(2) hallucination when retrieved context is ambiguous, "
                "(3) latency from multiple retrieval + generation steps, "
                "(4) difficulty handling multimodal content (tables, images, equations)."
            ),
            sources=["arxiv:2312.10997", "arxiv:2510.12323"],
            confidence=0.88,
        ),
    ]

    for i, finding in enumerate(simulated_answers):
        await asyncio.sleep(0.3)  # Simulate research time

        # Use lock to safely update findings
        async with VaultLock(vault, "findings", holder="researcher"):
            current = await vault.get("findings", model=ResearchFindings)
            current.findings.append(finding)
            if i == len(simulated_answers) - 1:
                current.status = "complete"
            await vault.put("findings", current, agent="researcher")

        print(f"[researcher] Found answer {i + 1}/{len(plan.questions)}: "
              f"confidence={finding.confidence:.0%}")

        # Store scratch notes with TTL (auto-cleanup)
        await vault.put(
            f"scratch:q{i}",
            f"Raw search results for: {finding.question}",
            agent="researcher",
            ttl=5,
        )

    await vault.put("pipeline_status", "research_complete", agent="researcher")
    print("[researcher] All research complete!")


async def writer_agent(vault: AsyncVault) -> None:
    """Synthesizes findings into a final report."""
    # Wait for research to complete
    print("[writer] Waiting for research to complete...")
    async for event in vault.watch("pipeline_status"):
        if event.new_value == "research_complete":
            break

    plan = await vault.get("plan", model=ResearchPlan)
    findings = await vault.get("findings", model=ResearchFindings)

    print(f"[writer] Got {len(findings.findings)} findings, writing report...")
    await asyncio.sleep(0.3)  # Simulate writing

    # Build report sections
    sections = []
    for finding in findings.findings:
        sections.append({
            "heading": finding.question,
            "body": finding.answer,
            "sources": ", ".join(finding.sources),
        })

    # Calculate total words
    total_words = sum(
        len(s["body"].split()) + len(s["heading"].split())
        for s in sections
    )

    report = Report(
        title=f"Research Report: {plan.topic}",
        sections=sections,
        word_count=total_words,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    await vault.put("report", report, agent="writer")
    await vault.put("pipeline_status", "report_complete", agent="writer")
    print(f"[writer] Report complete: {report.word_count} words, "
          f"{len(sections)} sections")


async def monitor_agent(vault: AsyncVault) -> None:
    """Monitors all vault activity (observability)."""
    event_count = 0
    async for event in vault.watch():
        if event.key.startswith("scratch:") or event.key.startswith("__lock:"):
            continue  # Skip internal keys
        icon = "+" if event.event_type == "put" else "-"
        print(f"  [{icon}] {event.key} v{event.version} <- {event.agent}")
        event_count += 1
        if event_count >= 8:
            break


# ── Main Pipeline ─────────────────────────────────────────────

async def main() -> None:
    vault = await AsyncVault.connect("research-demo", backend="memory")

    print("=" * 60)
    print("  Multi-Agent Research Pipeline with AgentVault")
    print("=" * 60)

    start = time.time()

    # Run all agents concurrently
    await asyncio.gather(
        planner_agent(vault),
        researcher_agent(vault),
        writer_agent(vault),
        monitor_agent(vault),
    )

    elapsed = time.time() - start

    # ── Final Summary ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Pipeline Complete!")
    print("=" * 60)

    print(f"\nTime: {elapsed:.1f}s")

    # Show final vault state
    print(f"\nVault contains {len(await vault.keys())} entries:")
    for key in await vault.keys():
        entry = await vault.get_entry(key)
        if entry:
            agent = entry.agent or "-"
            print(f"  {key:<25} v{entry.version}  by {agent}")

    # Show the report
    report = await vault.get("report", model=Report)
    print(f"\n--- {report.title} ---")
    for section in report.sections:
        print(f"\nQ: {section['heading']}")
        print(f"A: {section['body'][:100]}...")
        print(f"Sources: {section['sources']}")

    # Show audit trail for findings
    print("\n--- Audit Trail: findings ---")
    for entry in await vault.history("findings"):
        findings = ResearchFindings.model_validate(entry.value)
        print(f"  v{entry.version} by {entry.agent}: "
              f"{len(findings.findings)} findings, status={findings.status}")

    # Check scratch notes expired
    scratch_keys = [k for k in await vault.keys() if k.startswith("scratch:")]
    print(f"\nScratch notes remaining: {len(scratch_keys)} "
          f"(will auto-expire via TTL)")

    await vault.close()


if __name__ == "__main__":
    asyncio.run(main())
