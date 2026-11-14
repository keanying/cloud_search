from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.base import get_session
from ...db.models import BrowserSession, Evidence, SourceCandidate, SourceRevision
from ...orchestrator import control
from ...services.events import task_out
from ..deps import CurrentUser, current_user, get_task
from ..schemas import (
    BrowserSessionOut,
    CandidateOut,
    ConfirmIn,
    EvidenceOut,
    SourceOut,
    TaskOut,
    TaskSourcesOut,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _err(e: control.ControlError) -> HTTPException:
    return HTTPException(e.status, e.message)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task_api(task_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    return task_out(await get_task(s, u, task_id))


@router.post("/{task_id}/confirm", response_model=TaskOut)
async def confirm(task_id: str, body: ConfirmIn, u: CurrentUser = Depends(current_user),
                  s: AsyncSession = Depends(get_session)):
    t = await get_task(s, u, task_id)
    try:
        await control.confirm(s, t, body.plan_hash)
    except control.ControlError as e:
        raise _err(e) from None
    out = task_out(t)
    await s.commit()
    return out


@router.post("/{task_id}/stop", response_model=TaskOut)
async def stop(task_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    t = await get_task(s, u, task_id)
    await control.stop(s, t)
    out = task_out(t)
    await s.commit()
    return out


@router.post("/{task_id}/pause", response_model=TaskOut)
async def pause(task_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    t = await get_task(s, u, task_id)
    try:
        await control.pause(s, t)
    except control.ControlError as e:
        raise _err(e) from None
    out = task_out(t)
    await s.commit()
    return out


@router.post("/{task_id}/resume", response_model=TaskOut)
async def resume(task_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    t = await get_task(s, u, task_id)
    try:
        await control.resume(s, t)
    except control.ControlError as e:
        raise _err(e) from None
    out = task_out(t)
    await s.commit()
    return out


@router.post("/{task_id}/continue", response_model=TaskOut)
async def continue_task(task_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    t = await get_task(s, u, task_id)
    try:
        new = await control.continue_as_new(s, t, user_id=u.user_id)
    except control.ControlError as e:
        raise _err(e) from None
    out = task_out(new)
    await s.commit()
    return out


@router.get("/{task_id}/sources", response_model=TaskSourcesOut)
async def sources(task_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    await get_task(s, u, task_id)
    revs = (await s.execute(select(SourceRevision).where(SourceRevision.task_id == task_id)
                            .order_by(SourceRevision.source_no.is_(None), SourceRevision.source_no,
                                      SourceRevision.retrieved_time))).scalars().all()
    evs = (await s.execute(select(Evidence).where(Evidence.task_id == task_id)
                           .order_by(Evidence.created_time))).scalars().all()
    by_src: dict[str, list[EvidenceOut]] = {}
    for e in evs:
        by_src.setdefault(e.source_revision_id, []).append(EvidenceOut(
            evidence_id=e.evidence_id, quote_text=e.quote_text, claim_text=e.claim_text,
            verification_status=e.verification_status))
    out_sources = [SourceOut(n=r.source_no or 0, source_revision_id=r.source_revision_id, title=r.title,
                             request_url=r.request_url, final_url=r.final_url, site_name=r.site_name,
                             author=r.author, publish_time_text=r.publish_time_text, retrieved_time=r.retrieved_time,
                             access_method=r.access_method, revision_status=r.revision_status,
                             failure_reason=r.failure_reason, evidence=by_src.get(r.source_revision_id, []))
                   for r in revs]
    cands = (await s.execute(select(SourceCandidate).where(SourceCandidate.task_id == task_id)
                             .order_by(SourceCandidate.created_time, SourceCandidate.rank_no))).scalars().all()
    return TaskSourcesOut(sources=out_sources, candidates=[CandidateOut(
        candidate_id=c.candidate_id, query_text=c.query_text, engine_name=c.engine_name, rank_no=c.rank_no,
        url=c.url, title=c.title, snippet=c.snippet, candidate_status=c.candidate_status) for c in cands])


@router.get("/{task_id}/browser-sessions", response_model=list[BrowserSessionOut])
async def browser_sessions(task_id: str, u: CurrentUser = Depends(current_user),
                           s: AsyncSession = Depends(get_session)):
    """只列出真实存在的云端浏览器会话；查询本身不会创建会话。"""
    await get_task(s, u, task_id)
    rows = (await s.execute(select(BrowserSession).where(BrowserSession.task_id == task_id)
                            .order_by(BrowserSession.created_time))).scalars().all()
    from .viewer import live_available

    return [BrowserSessionOut(browser_session_id=r.browser_session_id, task_id=r.task_id,
                              session_label=r.session_label, session_status=r.session_status,
                              current_url=r.current_url, current_title=r.current_title,
                              current_activity=r.current_activity, frame_seq_no=r.frame_seq_no,
                              frame_time=r.frame_time, live_available=live_available(r),
                              handoff_state=r.handoff_state, handoff_reason=r.handoff_reason,
                              handoff_deadline=r.handoff_deadline) for r in rows]


@router.get("/{task_id}/trace")
async def task_trace(task_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    """下载任务执行日志（排查用）：任务与环境信息 + 逐行执行记录；旧任务没有日志文件时由数据库记录生成摘要。"""
    import platform
    from datetime import datetime
    from urllib.parse import quote

    from fastapi import Response

    from ...core.tracelog import config_summary, trace_path
    from ...db.models import AgentRun, TaskStep

    t = await get_task(s, u, task_id)
    head = [
        "云搜浏览器 · 任务执行日志",
        f"任务：{t.title}（{t.task_id}）",
        f"模式：{t.mode}　状态：{t.task_status}　当前阶段：{t.current_stage or '-'}",
        f"创建：{t.created_time}　更新：{t.updated_time}　模型调用：{t.llm_request_qty} 次",
        f"导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}　Python {platform.python_version()}　{platform.platform()}",
        f"版本：{_git_version()}",
        "配置摘要：" + __import__("json").dumps(config_summary(), ensure_ascii=False),
        "=" * 100,
    ]
    p = trace_path(task_id)
    if p.exists():
        body = p.read_text(encoding="utf-8", errors="replace")
    else:
        lines = ["（这个任务没有逐行执行日志——可能是在升级前运行的。以下根据数据库记录生成。）"]
        for st in (await s.execute(select(TaskStep).where(TaskStep.task_id == task_id)
                                   .order_by(TaskStep.created_time))).scalars():
            dur = (st.finished_time - st.started_time).total_seconds() if st.finished_time and st.started_time else None
            lines.append(f"{st.started_time}  [step]  {st.node_id} {st.step_status}"
                         f"{f'（{dur:.1f}s）' if dur is not None else ''}"
                         f"{'  错误：' + (st.error_desc or st.error_code or '')[:500] if st.step_status == 'failed' else ''}")
        for r in (await s.execute(select(AgentRun).where(AgentRun.task_id == task_id)
                                  .order_by(AgentRun.started_time))).scalars():
            lines.append(f"{r.started_time}  [llm]  {r.agent_role} · {r.model_name or ''} {r.run_status} "
                         f"tokens {r.input_token_qty}/{r.output_token_qty}"
                         f"{'  错误：' + (r.error_desc or '')[:500] if r.run_status != 'succeeded' else ''}")
        body = "\n".join(lines) + "\n"
    data = ("\n".join(head) + "\n" + body).encode("utf-8")
    name = f"执行日志_{t.title[:30]}_{task_id[-8:]}.log"
    return Response(data, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


def _git_version() -> str:
    from ...core.config import PROJECT_ROOT

    try:
        head = (PROJECT_ROOT / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1]
            sha = (PROJECT_ROOT / ".git" / ref).read_text().strip() if (PROJECT_ROOT / ".git" / ref).exists() else "?"
            return f"{ref.rsplit('/', 1)[-1]}@{sha[:8]}"
        return head[:8]
    except OSError:
        return "未知"
