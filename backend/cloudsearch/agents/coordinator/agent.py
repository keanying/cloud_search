from __future__ import annotations

from ...contracts import TaskSpec
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .plan import MAX_EXTRA_QUERIES
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import CoverageReview

SPEC: AgentSpec[CoverageReview] = AgentSpec(
    role=AgentRole.coordinator, output_type=CoverageReview, instructions=INSTRUCTIONS, request_limit=3)


def _norm(q: str) -> str:
    return "".join(sorted(q.lower().split()))


async def review_coverage(spec: TaskSpec, used_queries: list[str], evidence_digest: str,
                          ctx: ExecContext) -> CoverageReview:
    review = await run_agent(SPEC, build_prompt(spec_json=spec.model_dump_json(indent=1),
                                                used_queries=used_queries, evidence_digest=evidence_digest),
                             ctx=ctx)
    used = {_norm(q) for q in used_queries}
    seen: set[str] = set()
    extra = []
    for q in review.extra_queries:
        k = _norm(q)
        if q.strip() and k not in used and k not in seen:
            seen.add(k)
            extra.append(q.strip())
    review.extra_queries = extra[:MAX_EXTRA_QUERIES]
    if review.sufficient:
        review.extra_queries = []
    return review
