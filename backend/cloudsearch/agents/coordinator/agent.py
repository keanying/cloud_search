from __future__ import annotations

from ...contracts import SearchQuery, TaskSpec
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .plan import MAX_EXTRA_QUERIES
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import CoverageReview

SPEC: AgentSpec[CoverageReview] = AgentSpec(
    role=AgentRole.coordinator, output_type=CoverageReview, instructions=INSTRUCTIONS, request_limit=3)


def _norm(q: str) -> str:
    return "".join(sorted(q.lower().replace('"', "").split()))


async def review_coverage(spec: TaskSpec, used_queries: list[str], evidence_digest: str, ctx: ExecContext, *,
                          sub_questions: list[str] | None = None, empty_aspects: list[str] | None = None,
                          wave: int = 1, max_waves: int = 1) -> CoverageReview:
    """评估覆盖度并给出补查。empty_aspects：程序统计出“没有任何证据”的子问题——模型判断充分时也会为它们补查。"""
    review = await run_agent(SPEC, build_prompt(spec_json=spec.model_dump_json(indent=1),
                                                sub_questions=sub_questions or [], used_queries=used_queries,
                                                evidence_digest=evidence_digest, wave=wave, max_waves=max_waves),
                             ctx=ctx)
    used = {_norm(q) for q in used_queries}
    seen: set[str] = set()
    extra: list[SearchQuery] = []
    candidates = list(review.extra_queries)
    lang = "zh" if spec.scope.language.startswith("zh") else "en"
    # 程序兜底：完全没有证据的子问题必须补查（模型可能误判为充分）
    for asp in empty_aspects or []:
        if not any(q.purpose == asp for q in candidates):
            candidates.append(SearchQuery(query=asp[:60], purpose=asp, language=lang))
    for q in candidates:
        k = _norm(q.query)
        if q.query.strip() and k not in used and k not in seen:
            seen.add(k)
            extra.append(q)
    review.extra_queries = extra[:MAX_EXTRA_QUERIES]
    if empty_aspects:
        review.sufficient = False
        review.missing_aspects = list(dict.fromkeys([*review.missing_aspects, *empty_aspects]))
    if review.sufficient:
        review.extra_queries = []
    return review
