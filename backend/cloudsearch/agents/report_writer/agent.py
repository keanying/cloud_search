from __future__ import annotations

import asyncio
import json
import re

from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import (
    INSTRUCTIONS,
    SECTION_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
    build_prompt,
    build_section_prompt,
    build_synthesis_prompt,
)
from .schemas import ChartSpec, Highlight, ReportDraft, SectionDraft, TimelineItem

SPEC: AgentSpec[ReportDraft] = AgentSpec(
    role=AgentRole.report_writer, output_type=ReportDraft, instructions=INSTRUCTIONS, request_limit=4)
SECTION_SPEC: AgentSpec[SectionDraft] = AgentSpec(
    role=AgentRole.report_writer, output_type=SectionDraft, instructions=SECTION_INSTRUCTIONS, request_limit=3)
SYNTHESIS_SPEC: AgentSpec[ReportDraft] = AgentSpec(
    role=AgentRole.report_writer, output_type=ReportDraft, instructions=SYNTHESIS_INSTRUCTIONS, request_limit=4)
CN_NUM = "一二三四五六七八九十"


def cn_no(i: int) -> str:
    """0 → 一 … 9 → 十；更多章节用阿拉伯数字。"""
    return CN_NUM[i] if i < len(CN_NUM) else str(i + 1)

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
    for c in charts[:6]:
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


_YEAR = re.compile(r"(1[89]\d{2}|20\d{2})")


def verify_timeline(items: list[TimelineItem], evidence_by_n: dict[int, str]) -> list[TimelineItem]:
    """时间轴核对：日期里的年份（没有年份时整段日期）必须出现在该来源的证据中；按年份排序，去重，最多 12 条。"""
    kept: list[TimelineItem] = []
    seen: set[tuple[str, str]] = set()
    for it in items[:16]:
        src = evidence_by_n.get(it.source_n, "")
        date, title = (it.date or "").strip(), (it.title or "").strip()
        if not src or not date or not title:
            continue
        years = _YEAR.findall(date)
        if not (all(y in src for y in years) if years else date in src):
            continue
        key = (date, title)
        if key in seen:
            continue
        seen.add(key)
        kept.append(it.model_copy(update={"date": date, "title": title[:24],
                                          "detail": (it.detail or "").strip()[:60] or None}))

    def year(it: TimelineItem) -> int:
        m = _YEAR.search(it.date)
        return int(m.group(1)) if m else 9999

    return sorted(kept, key=year)[:12]


def timeline_fence(items: list[TimelineItem], title: str = "关键时间节点") -> str:
    payload = {"title": title, "items": [i.model_dump() for i in items]}
    return "```timeline\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


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
    if draft.timeline:
        parts.append(timeline_fence(draft.timeline))
    parts.append(body)
    rest = [chart_fence(c) for c in charts if c.id not in placed]
    if rest:
        parts.append("\n\n".join(rest))
    if draft.limitations:
        parts.append("## 局限与说明\n\n" + "\n".join(f"- {x}" for x in draft.limitations))
    return "\n\n".join(p for p in parts if p).strip() + "\n"


async def write(*, kind: str, question: str, outline: list[str], audience: str | None, evidence_block: str,
                valid_ns: set[int], analysis_block: str, conflicts_block: str, gaps_block: str,
                ctx: ExecContext, today: str = "", evidence_by_n: dict[int, str] | None = None,
                on_partial=None) -> tuple[ReportDraft, list[int], list[ChartSpec]]:
    """on_partial：撰写过程中收到部分草稿（ReportDraft）的回调，用于实时显示。"""
    draft = await run_agent(SPEC, build_prompt(kind=kind, question=question, outline=outline, audience=audience,
                                               evidence_block=evidence_block, analysis_block=analysis_block,
                                               conflicts_block=conflicts_block, gaps_block=gaps_block, today=today),
                            ctx=ctx, on_partial=on_partial)
    return finalize(draft, valid_ns=valid_ns, evidence_block=evidence_block, analysis_block=analysis_block,
                    evidence_by_n=evidence_by_n or {})


def finalize(draft: ReportDraft, *, valid_ns: set[int], evidence_block: str, analysis_block: str,
             evidence_by_n: dict[int, str]) -> tuple[ReportDraft, list[int], list[ChartSpec]]:
    """核对关键数字、时间轴与图表，清理无效引用；返回（草稿, 实际引用的来源序号, 保留的图表）。"""
    draft.highlights = verify_highlights([h for h in draft.highlights if h.source_n in valid_ns],
                                         evidence_by_n, analysis_block)
    draft.timeline = verify_timeline([t for t in draft.timeline if t.source_n in valid_ns], evidence_by_n)
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
    used = sorted(set(u1) | set(u2) | set(used) | {t.source_n for t in draft.timeline})
    return draft, used, charts


def _prefix_charts(markdown: str, charts: list[ChartSpec], prefix: str) -> tuple[str, list[ChartSpec]]:
    """分章撰写时各章的图表编号可能重复：统一加章前缀。"""
    ids = {c.id for c in charts}
    md = _CHART_REF.sub(lambda m: f"[[chart:{prefix}{m.group(1)}]]" if m.group(1) in ids else "", markdown)
    return md, [c.model_copy(update={"id": f"{prefix}{c.id}"}) for c in charts]


async def write_sectioned(*, question: str, sections: list[str], section_evidence: list[str], audience: str | None,
                          evidence_block: str, valid_ns: set[int], analysis_block: str, conflicts_block: str,
                          gaps_block: str, ctx: ExecContext, today: str = "",
                          evidence_by_n: dict[int, str] | None = None, on_partial=None,
                          concurrency: int = 3) -> tuple[ReportDraft, list[int], list[ChartSpec]]:
    """深度报告：按提纲逐章撰写（每章只看本章证据，可并行），再写综合分析章、标题、摘要、要点与时间轴。
    比一次写完篇幅更长、每章论述更充分；模型调用次数为 章数 + 1。"""
    sem = asyncio.Semaphore(max(1, concurrency))
    texts: dict[int, str] = {}

    async def publish(extra_title: str = "") -> None:
        if on_partial is None:
            return
        body = "\n\n".join(texts[i] for i in sorted(texts))
        await on_partial(ReportDraft(title=extra_title, markdown=body))

    async def one(i: int) -> SectionDraft:
        async def part(d) -> None:
            texts[i] = f"## {cn_no(i)}、{getattr(d, 'heading', '') or ''}\n\n{getattr(d, 'markdown', '') or ''}"
            await publish()

        async with sem:
            return await run_agent(SECTION_SPEC, build_section_prompt(
                question=question, outline=sections, index=i, chapter_no=cn_no(i),
                evidence_block=section_evidence[i], today=today, audience=audience),
                ctx=ctx, on_partial=part if on_partial else None)

    drafts = await asyncio.gather(*(one(i) for i in range(len(sections))))
    chapters, all_charts = [], []
    for i, d in enumerate(drafts):
        md, charts = _prefix_charts(d.markdown, d.charts[:1], f"s{i + 1}_")
        chapters.append(f"## {cn_no(i)}、{d.heading.strip() or sections[i]}\n\n{md.strip()}")
        all_charts += charts
        texts[i] = chapters[-1]
    final_heading = f"## {cn_no(len(sections))}、综合分析"
    chapters_md = "\n\n".join(chapters)
    synth = await run_agent(SYNTHESIS_SPEC, build_synthesis_prompt(
        question=question, chapters_md=chapters_md, final_heading=final_heading, evidence_block=evidence_block,
        analysis_block=analysis_block, conflicts_block=conflicts_block, gaps_block=gaps_block, today=today,
        audience=audience), ctx=ctx)
    closing = synth.markdown.strip()
    if closing and not closing.startswith("## "):
        closing = f"{final_heading}\n\n{closing}"
    synth_md, synth_charts = _prefix_charts(closing, synth.charts[:1], "z_")
    synth.markdown = chapters_md + ("\n\n" + synth_md if synth_md else "")
    synth.charts = all_charts + synth_charts
    return finalize(synth, valid_ns=valid_ns, evidence_block=evidence_block + "\n" + "\n".join(section_evidence),
                    analysis_block=analysis_block, evidence_by_n=evidence_by_n or {})
