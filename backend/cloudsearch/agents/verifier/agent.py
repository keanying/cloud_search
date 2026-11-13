from __future__ import annotations

from ...contracts import EvidenceRef
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import ConflictReport

SPEC: AgentSpec[ConflictReport] = AgentSpec(
    role=AgentRole.verifier, output_type=ConflictReport, instructions=INSTRUCTIONS, request_limit=3)

MAX_EVIDENCE_FOR_MODEL = 80


async def cross_check(evidence: list[EvidenceRef], ctx: ExecContext) -> ConflictReport:
    """跨来源核验。证据编号为列表下标+1。"""
    if not evidence:
        return ConflictReport()
    lines = "\n".join(f"{i + 1} | [{e.n}] | {e.claim} | {e.quote[:220]}"
                      for i, e in enumerate(evidence[:MAX_EVIDENCE_FOR_MODEL]))
    report = await run_agent(SPEC, build_prompt(lines), ctx=ctx)
    valid = set(range(1, min(len(evidence), MAX_EVIDENCE_FOR_MODEL) + 1))
    report.unsupported = [i for i in report.unsupported if i in valid]
    for c in report.conflicts:
        c.evidence_nos = [i for i in c.evidence_nos if i in valid]
    report.conflicts = [c for c in report.conflicts if len(c.evidence_nos) >= 2]
    return report
