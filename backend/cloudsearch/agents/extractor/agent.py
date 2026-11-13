from __future__ import annotations

from ...contracts import SourceDoc, TaskSpec
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .passages import select_passages
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


async def extract(source: SourceDoc, spec: TaskSpec, ctx: ExecContext, *, sub_questions: list[str] | None = None,
                  key_entities: list[str] | None = None) -> ExtractionOutput:
    header = f"[{source.n}] {source.title or ''} {source.url}"
    if source.publish_time_text:
        header += f"（页面声明发布时间：{source.publish_time_text}）"
    terms = [*spec.scope.questions, *spec.scope.items, *(sub_questions or []), *(key_entities or []), spec.title]
    if spec.dataset:
        terms += [f.label for f in spec.dataset.fields] + [spec.dataset.entity]
    # 长网页：按相关度挑段落（摘录校验仍针对完整正文）
    text = select_passages(source.text, terms, budget=MAX_TEXT_FOR_MODEL)
    task_desc = describe_task(spec)
    if sub_questions:
        task_desc += "\n子问题（aspect 请填写其中最贴切的一个，原文照抄）：\n" + "\n".join(f"- {q}" for q in sub_questions)
    prompt = build_prompt(task_desc=task_desc, fields_desc=describe_fields(spec), source_header=header, text=text)
    out = await run_agent(SPEC, prompt, ctx=ctx)
    out.findings = out.findings[:12]
    out.records = out.records[:20] if spec.dataset else []
    if spec.dataset:
        keys = {f.key for f in spec.dataset.fields}
        for r in out.records:  # 丢弃未定义字段，缺失字段补 null
            r.values = {k: r.values.get(k) for k in keys}
            r.quotes = {k: v for k, v in r.quotes.items() if k in keys}
    return out
