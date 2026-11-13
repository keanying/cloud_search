from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

from ...contracts import SearchHit, SearchQuery, TaskSpec
from ...search.service import describe_sources, vertical_sources
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import (
    PLAN_INSTRUCTIONS,
    REFINE_INSTRUCTIONS,
    SELECT_INSTRUCTIONS,
    build_plan_prompt,
    build_refine_prompt,
    build_select_prompt,
)
from .schemas import CandidateSelection, QueryPlan, QueryRefinement

SPEC: AgentSpec[QueryPlan] = AgentSpec(
    role=AgentRole.search_planner, output_type=QueryPlan, instructions=PLAN_INSTRUCTIONS, request_limit=3)
SELECT_SPEC: AgentSpec[CandidateSelection] = AgentSpec(
    role=AgentRole.search_planner, output_type=CandidateSelection, instructions=SELECT_INSTRUCTIONS, request_limit=3)
REFINE_SPEC: AgentSpec[QueryRefinement] = AgentSpec(
    role=AgentRole.search_planner, output_type=QueryRefinement, instructions=REFINE_INSTRUCTIONS, request_limit=3)

MAX_SELECT_CANDIDATES = 40
MAX_REFINE = 3


def _key(q: str) -> str:
    return "".join(sorted(re.sub(r'["“”]', "", q).lower().split()))


def dedupe_queries(queries: list, limit: int) -> list:
    """去重（忽略大小写、引号与词序），保持顺序，截断到上限。接受字符串或 SearchQuery。"""
    seen: set[str] = set()
    out: list = []
    for q in queries:
        text = q.query if isinstance(q, SearchQuery) else q
        text = " ".join(str(text).split())
        k = _key(text)
        if text and k not in seen:
            seen.add(k)
            if isinstance(q, SearchQuery):
                q.query = text
                out.append(q)
            else:
                out.append(text)
    return out[:limit]


def _ensure_coverage(spec: TaskSpec, plan: QueryPlan) -> list[SearchQuery]:
    """确定性补充：用户点名的对象、用户指定的站点必须被覆盖。"""
    limit = spec.limits.max_queries
    queries = dedupe_queries(plan.queries, limit)
    lang = "zh" if spec.scope.language.startswith("zh") else "en"
    texts = " ".join(q.query for q in queries)
    for item in spec.scope.items:
        if item not in texts and len(queries) < limit:
            queries.append(SearchQuery(query=item, purpose=f"覆盖用户点名的对象：{item}", language=lang))
    core = " ".join(plan.key_entities[:2]) or (spec.scope.questions[0] if spec.scope.questions else spec.title)
    for domain in spec.scope.include_domains[:3]:
        if f"site:{domain}" not in texts:
            q = SearchQuery(query=f"site:{domain} {core}"[:120], purpose=f"用户指定的来源 {domain}", language=lang)
            if len(queries) < limit:
                queries.append(q)
            else:
                queries[-1] = q
    return dedupe_queries(queries, limit)


async def plan_queries(spec: TaskSpec, ctx: ExecContext) -> QueryPlan:
    plan = await run_agent(SPEC, build_plan_prompt(spec_json=spec.model_dump_json(indent=1),
                                                   max_queries=spec.limits.max_queries,
                                                   today=date.today().isoformat(),
                                                   sources=describe_sources()), ctx=ctx)
    valid_sources = set(vertical_sources())
    for q in plan.queries:  # 未知来源 → 通用引擎；垂直来源不支持 site: 等语法
        if q.source and q.source not in valid_sources:
            q.source = None
        if q.source:
            q.query = re.sub(r'(-?site:\S+|["“”])', " ", q.query).strip() or q.query
    plan.queries = _ensure_coverage(spec, plan)
    plan.preferred_sources = [d.lower().strip().lstrip(".") for d in plan.preferred_sources if "." in d][:8]
    return plan


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


async def select_candidates(spec: TaskSpec, intent: str, hits: list[SearchHit], limit: int,
                            ctx: ExecContext) -> list[tuple[int, str]]:
    """让模型按意图与来源权威性挑选要读的候选；返回 [(原列表下标, 理由)]，由程序校验编号。"""
    shown = hits[:MAX_SELECT_CANDIDATES]
    lines = "\n".join(f"{i} | {(h.title or '')[:60]} | {_domain(h.url)} | {(h.snippet or '')[:100]} | {h.query[:40]}"
                      for i, h in enumerate(shown))
    out = await run_agent(SELECT_SPEC, build_select_prompt(intent=intent, spec_json=spec.model_dump_json(),
                                                           candidates=lines, limit=limit), ctx=ctx)
    picked: list[tuple[int, str]] = []
    seen: set[int] = set()
    for c in out.selected:
        if 0 <= c.index < len(shown) and c.index not in seen:
            seen.add(c.index)
            picked.append((c.index, c.reason))
        if len(picked) >= limit:
            break
    return picked


async def refine_queries(spec: TaskSpec, intent: str, weak: list[tuple[str, list[str]]], used: list[str],
                         ctx: ExecContext) -> list[SearchQuery]:
    """改写无结果/结果无关的查询（每轮最多 MAX_REFINE 条，不与已用查询重复）。"""
    text = "\n".join(f"- {q}（返回：{'；'.join(t[:40] for t in titles[:3]) or '无结果'}）" for q, titles in weak)
    out = await run_agent(REFINE_SPEC, build_refine_prompt(intent=intent, weak=text), ctx=ctx)
    used_keys = {_key(u) for u in used}
    fresh = [q for q in dedupe_queries(out.queries, MAX_REFINE) if _key(q.query) not in used_keys]
    return fresh[:MAX_REFINE]
