from __future__ import annotations

import json
from typing import Any

from ...contracts import TaskSpec
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .compute import InvalidAnalysis, run_analysis
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import AnalysisPlan, AnalysisResult

SPEC: AgentSpec[AnalysisPlan] = AgentSpec(
    role=AgentRole.analyst, output_type=AnalysisPlan, instructions=INSTRUCTIONS, request_limit=3)


async def analyze(spec: TaskSpec, records: list[dict[str, Any]], ctx: ExecContext) -> list[AnalysisResult]:
    assert spec.dataset is not None
    if not records:
        return []
    fields_desc = "\n".join(f"- {f.key}（{f.label}，{f.type}）" for f in spec.dataset.fields)
    request = spec.dataset.analysis_request or (spec.report.question if spec.report else spec.requirement_text)
    plan = await run_agent(SPEC, build_prompt(request=request, entity=spec.dataset.entity, fields_desc=fields_desc,
                                              sample=json.dumps(records[:5], ensure_ascii=False, default=str),
                                              row_qty=len(records)), ctx=ctx)
    results: list[AnalysisResult] = []
    for a in plan.analyses[:5]:
        try:
            results.append(run_analysis(records, spec.dataset.fields, a))
        except (InvalidAnalysis, Exception) as e:  # noqa: BLE001  无效方案跳过并记录，不由模型补数
            results.append(AnalysisResult(title=a.title, description=a.description, columns=[], rows=[], sql="",
                                          warnings=[f"计算方案无效，已跳过：{e}"]))
    return results
