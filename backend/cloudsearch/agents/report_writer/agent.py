from __future__ import annotations

import re

from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import ReportDraft

SPEC: AgentSpec[ReportDraft] = AgentSpec(
    role=AgentRole.report_writer, output_type=ReportDraft, instructions=INSTRUCTIONS, request_limit=4)

_CITE = re.compile(r"\[(\d{1,3}(?:\s*[,，、]\s*\d{1,3})*)\]")


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


async def write(*, kind: str, question: str, outline: list[str], audience: str | None, evidence_block: str,
                valid_ns: set[int], analysis_block: str, conflicts_block: str, gaps_block: str,
                ctx: ExecContext) -> tuple[ReportDraft, list[int]]:
    draft = await run_agent(SPEC, build_prompt(kind=kind, question=question, outline=outline, audience=audience,
                                               evidence_block=evidence_block, analysis_block=analysis_block,
                                               conflicts_block=conflicts_block, gaps_block=gaps_block), ctx=ctx)
    draft.markdown, used = sanitize_citations(draft.markdown, valid_ns)
    return draft, used
