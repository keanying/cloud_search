from __future__ import annotations

import json
import re

from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import ChartSpec, Highlight, ReportDraft

SPEC: AgentSpec[ReportDraft] = AgentSpec(
    role=AgentRole.report_writer, output_type=ReportDraft, instructions=INSTRUCTIONS, request_limit=4)

_CITE = re.compile(r"\[(\d{1,3}(?:\s*[,，、]\s*\d{1,3})*)\]")
_NUM = re.compile(r"-?\d[\d,，]*(?:\.\d+)?")
_CHART_REF = re.compile(r"\[\[chart:([A-Za-z0-9_-]+)\]\]")


def sanitize_citations(markdown: str, valid: set[int]) -> tuple[str, list[int]]:
    """删除不存在的引用序号，返回（清理后的正文, 实际使用的序号）。"""
    used: list[int] = []

    def repl(m: re.Match) -> str:
        ns = [int(x) for x in re.split(r"[,，、\s]+", m.group(1)) if x]
        ok = [n for n in ns if n in valid]
        for n in ok:
            if n not in used:
                used.append(n)
        return "".join(f"[{n}]" for n in ok)

    return _CITE.sub(repl, markdown), sorted(used)


def _numbers(text: str) -> set[float]:
    out: set[float] = set()
    for m in _NUM.findall(text):
        try:
            out.add(round(float(m.replace(",", "").replace("，", "")), 6))
        except ValueError:
            pass
    return out


def verify_charts(charts: list[ChartSpec], source_text: str) -> tuple[list[ChartSpec], list[str]]:
    """图表数据核对：每个非空数值都必须出现在证据或计算结果中；否则删除该图表。"""
    known = _numbers(source_text)
    kept, dropped = [], []
    for c in charts[:3]:
        n_cat = len(c.categories)
        values = [v for s in c.series for v in s.values if v is not None]
        shape_ok = all(len(s.values) == n_cat for s in c.series) and values
        if shape_ok and all(round(float(v), 6) in known for v in values):
            kept.append(c)
        else:
            dropped.append(c.title)
    return kept, dropped


def verify_highlights(items: list[Highlight], evidence_by_n: dict[int, str], analysis_text: str
                      ) -> list[Highlight]:
    """关键数字核对：数值必须出现在对应来源的证据（或计算结果）中。"""
    kept = []
    for h in items[:4]:
        nums = _numbers(h.value)
        src = evidence_by_n.get(h.source_n, "")
        if not nums or not src:
            continue
        known = _numbers(src + "\n" + analysis_text)
        if all(n in known for n in nums):
            kept.append(h)
    return kept


def chart_fence(c: ChartSpec) -> str:
    payload = {"type": c.type, "title": c.title, "unit": c.unit, "categories": c.categories,
               "series": [s.model_dump() for s in c.series], "source": c.source}
    return "```chart\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def highlights_markdown(items: list[Highlight]) -> str:
    if not items:
        return ""
    rows = "\n".join(f"| {h.label} | **{h.value}**{(' ' + h.unit) if h.unit else ''} | [{h.source_n}] |" for h in items)
    return "**关键数字**\n\n| 指标 | 数值 | 来源 |\n|---|---|---|\n" + rows


def assemble_markdown(draft: ReportDraft, charts: list[ChartSpec], *, include_title: bool,
                      with_highlights: bool = False) -> str:
    """组装成完整 Markdown：标题 → 摘要 → 要点 → 正文（图表就位）→ 局限。"""
    by_id = {c.id: c for c in charts}
    placed: set[str] = set()

    def place(m: re.Match) -> str:
        c = by_id.get(m.group(1))
        if c is None:
            return ""
        placed.add(c.id)
        return "\n\n" + chart_fence(c) + "\n\n"

    body = _CHART_REF.sub(place, draft.markdown).strip()
    parts = []
    if include_title and draft.title:
        parts.append(f"# {draft.title}")
    if draft.summary:
        parts.append("> **摘要**　" + draft.summary.strip())
    if with_highlights and draft.highlights:
        parts.append(highlights_markdown(draft.highlights))
    if draft.key_points:
        parts.append("**要点**\n\n" + "\n".join(f"- {p.strip()}" for p in draft.key_points if p.strip()))
    parts.append(body)
    rest = [chart_fence(c) for c in charts if c.id not in placed]
    if rest:
        parts.append("\n\n".join(rest))
    if draft.limitations:
        parts.append("## 局限与说明\n\n" + "\n".join(f"- {x}" for x in draft.limitations))
    return "\n\n".join(p for p in parts if p).strip() + "\n"


async def write(*, kind: str, question: str, outline: list[str], audience: str | None, evidence_block: str,
                valid_ns: set[int], analysis_block: str, conflicts_block: str, gaps_block: str,
                ctx: ExecContext, today: str = "", evidence_by_n: dict[int, str] | None = None
                ) -> tuple[ReportDraft, list[int], list[ChartSpec]]:
    draft = await run_agent(SPEC, build_prompt(kind=kind, question=question, outline=outline, audience=audience,
                                               evidence_block=evidence_block, analysis_block=analysis_block,
                                               conflicts_block=conflicts_block, gaps_block=gaps_block, today=today),
                            ctx=ctx)
    draft.highlights = verify_highlights([h for h in draft.highlights if h.source_n in valid_ns],
                                         evidence_by_n or {}, analysis_block)
    draft.follow_ups = [q.strip() for q in draft.follow_ups if q.strip()][:3]
    charts, dropped = verify_charts(draft.charts, evidence_block + "\n" + analysis_block)
    if dropped:
        draft.limitations.append(f"以下图表的数据无法与来源逐一核对，已省略：{'、'.join(dropped)}")
    used: list[int] = []
    draft.summary, u1 = sanitize_citations(draft.summary, valid_ns)
    draft.key_points = [sanitize_citations(p, valid_ns)[0] for p in draft.key_points]
    draft.markdown, u2 = sanitize_citations(draft.markdown, valid_ns)
    for p in draft.key_points:
        used += sanitize_citations(p, valid_ns)[1]
    used = sorted(set(u1) | set(u2) | set(used))
    return draft, used, charts
