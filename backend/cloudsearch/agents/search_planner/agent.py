from __future__ import annotations

from ...contracts import TaskSpec
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import QueryPlan

SPEC: AgentSpec[QueryPlan] = AgentSpec(
    role=AgentRole.search_planner, output_type=QueryPlan, instructions=INSTRUCTIONS, request_limit=3)


def dedupe_queries(queries: list[str], limit: int) -> list[str]:
    """去重（忽略大小写与词序），保持顺序，截断到上限。"""
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = " ".join(q.split())
        k = "".join(sorted(q.lower().split()))
        if q and k not in seen:
            seen.add(k)
            out.append(q)
    return out[:limit]


async def plan_queries(spec: TaskSpec, ctx: ExecContext) -> list[str]:
    plan = await run_agent(SPEC, build_prompt(spec_json=spec.model_dump_json(indent=1),
                                              max_queries=spec.limits.max_queries), ctx=ctx)
    queries = dedupe_queries([q.query for q in plan.queries], spec.limits.max_queries)
    # 用户点名的对象确保被覆盖
    for item in spec.scope.items:
        if not any(item in q for q in queries) and len(queries) < spec.limits.max_queries:
            queries.append(item)
    return queries
