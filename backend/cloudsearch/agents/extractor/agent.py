from __future__ import annotations

from ...contracts import SourceDoc, TaskSpec
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import ExtractionOutput

SPEC: AgentSpec[ExtractionOutput] = AgentSpec(
    role=AgentRole.extractor, output_type=ExtractionOutput, instructions=INSTRUCTIONS, request_limit=4)

MAX_TEXT_FOR_MODEL = 14000


def describe_task(spec: TaskSpec) -> str:
    lines = [f"标题：{spec.title}", f"原始需求：{spec.requirement_text}"]
    if spec.scope.questions:
        lines.append("问题：" + "；".join(spec.scope.questions))
    if spec.scope.items:
        lines.append("关注对象：" + "、".join(spec.scope.items))
    if spec.dataset:
        lines.append(f"记录粒度：{spec.dataset.entity}")
    return "\n".join(lines)


def describe_fields(spec: TaskSpec) -> str | None:
    if not spec.dataset:
        return None
    return "\n".join(f"- {f.key}（{f.label}，{f.type}{'，必填' if f.required else ''}"
                     f"{'，单位' + f.unit if f.unit else ''}）{f.description or ''}" for f in spec.dataset.fields)


async def extract(source: SourceDoc, spec: TaskSpec, ctx: ExecContext) -> ExtractionOutput:
    header = f"[{source.n}] {source.title or ''} {source.url}"
    prompt = build_prompt(task_desc=describe_task(spec), fields_desc=describe_fields(spec),
                          source_header=header, text=source.text[:MAX_TEXT_FOR_MODEL])
    out = await run_agent(SPEC, prompt, ctx=ctx)
    out.findings = out.findings[:12]
    out.records = out.records[:20] if spec.dataset else []
    if spec.dataset:
        keys = {f.key for f in spec.dataset.fields}
        for r in out.records:  # 丢弃未定义字段，缺失字段补 null
            r.values = {k: r.values.get(k) for k in keys}
            r.quotes = {k: v for k, v in r.quotes.items() if k in keys}
    return out
