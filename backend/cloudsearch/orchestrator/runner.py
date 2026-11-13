"""执行一次 TaskRun：租约心跳、流水线、终态收敛（completed/partial_failed/failed/stopped/paused）。"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from ..contracts import TaskSpec
from ..core.config import get_settings
from ..core.ids import utcnow
from ..db.base import is_mysql, session_scope
from ..db.models import Task, TaskRun
from .context import BudgetExhausted, LeaseLost, TaskExecContext, TaskInterrupted
from .pipeline import Pipeline
from .progress import project_task

log = logging.getLogger(__name__)


async def claim_run(worker_id: str) -> tuple[str, int] | None:
    """领取一个排队中（或租约过期）的运行。返回 (run_id, lease_epoch)。"""
    s_ = get_settings()
    now = utcnow()
    async with session_scope() as s:
        q = (select(TaskRun).where(or_(TaskRun.run_status == "queued",
                                       and_(TaskRun.run_status == "running", TaskRun.lease_expire_time < now)))
             .order_by(TaskRun.created_time).limit(1))
        if is_mysql():
            q = q.with_for_update(skip_locked=True)
        run = (await s.execute(q)).scalar()
        if run is None:
            return None
        task = await s.get(Task, run.task_id)
        if task is None or task.cancel_generation != run.cancel_generation:
            run.run_status = "cancelled"
            run.finished_time = now
            return None
        run.worker_id = worker_id
        run.lease_epoch += 1
        run.lease_expire_time = now + timedelta(seconds=s_.worker_lease_s)
        run.run_status = "running"
        run.started_time = run.started_time or now
        if task.task_status in ("queued", "running"):
            task.task_status = "running"
            await project_task(s, task, task_event="run_started", detail={"run_id": run.run_id})
        return run.run_id, run.lease_epoch


async def _heartbeat(ctx: TaskExecContext, stop: asyncio.Event) -> None:
    s_ = get_settings()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(5, s_.worker_lease_s // 3))
            return
        except TimeoutError:
            pass
        async with session_scope() as s:
            res = await s.execute(update(TaskRun).where(
                TaskRun.run_id == ctx.run_id, TaskRun.lease_epoch == ctx.lease_epoch,
                TaskRun.worker_id == ctx.worker_id).values(
                lease_expire_time=utcnow() + timedelta(seconds=s_.worker_lease_s)))
            if res.rowcount == 0:
                ctx.lost = True
                return


async def execute_run(run_id: str, lease_epoch: int, worker_id: str) -> None:
    async with session_scope() as s:
        run = await s.get(TaskRun, run_id)
        task = await s.get(Task, run.task_id)
        spec = TaskSpec.model_validate(task.task_spec)
        ctx = TaskExecContext(task_id=task.task_id, run_id=run_id, project_id=task.project_id, worker_id=worker_id,
                              cancel_generation=run.cancel_generation, lease_epoch=lease_epoch,
                              max_llm_requests=spec.limits.max_llm_requests,
                              budget_limit_minor_amt=task.budget_limit_minor_amt)
        conversation_id = task.conversation_id
    stop_hb = asyncio.Event()
    hb = asyncio.create_task(_heartbeat(ctx, stop_hb))
    try:
        outcome = await Pipeline(ctx, spec, conversation_id=conversation_id).run()
    except LeaseLost:
        log.warning("lease lost for run %s; abandoning without state changes", run_id)
        return
    except TaskInterrupted as e:
        await _finish_interrupted(ctx, e.kind)
        return
    except BudgetExhausted as e:
        await _finish(ctx, "partial_failed", error_code="budget_exhausted", error_desc=str(e),
                      parts=[{"type": "error", "part_id": f"error-{ctx.task_id}", "code": "budget_exhausted",
                              "message": f"已达到本任务的额度上限（{e}），已停止新的模型调用；已读取的来源保留。",
                              "task_id": ctx.task_id}])
        return
    except Exception as e:  # noqa: BLE001
        log.exception("run %s failed", run_id)
        await _finish(ctx, "failed", error_code=type(e).__name__, error_desc=str(e)[:2000],
                      parts=[{"type": "error", "part_id": f"error-{ctx.task_id}", "code": type(e).__name__,
                              "message": _friendly_error(e), "task_id": ctx.task_id}])
        return
    finally:
        stop_hb.set()
        hb.cancel()

    # 单个网页受限/失败属于覆盖缺口（在成果中说明），不使整个任务失败；没有任何可交付成果才是 failed
    status = "completed" if outcome.delivered else "failed"
    await _finish(ctx, status, error_code=outcome.error_code, error_desc=outcome.error_desc, parts=outcome.parts,
                  artifact_ids=outcome.artifact_ids)


def _friendly_error(e: Exception) -> str:
    from ..llm.registry import LlmNotConfigured

    if isinstance(e, LlmNotConfigured):
        return str(e)
    return f"任务执行出错：{type(e).__name__}。已保存的来源与成果不受影响，可稍后重试。"


async def _artifact_parts(s, task_id: str, artifact_ids: list[str]) -> list[dict]:
    from ..db.models import Artifact

    if not artifact_ids:
        return []
    rows = (await s.execute(select(Artifact).where(Artifact.artifact_id.in_(artifact_ids)))).scalars().all()
    by_id = {a.artifact_id: a for a in rows}
    return [{"type": "artifact", "part_id": f"artifact-{a.artifact_id}", "task_id": task_id,
             "artifact_id": a.artifact_id, "artifact_kind": a.artifact_kind, "display_name": a.display_name,
             "mime_name": a.mime_name, "byte_qty": a.byte_qty, "record_qty": a.record_qty,
             "content_hash": a.content_hash, "quality_status": a.quality_status}
            for aid in artifact_ids if (a := by_id.get(aid))]


async def _finish(ctx: TaskExecContext, status: str, *, error_code: str | None = None, error_desc: str | None = None,
                  parts: list[dict] | None = None, artifact_ids: list[str] | None = None) -> None:
    async with session_scope() as s:
        run = await s.get(TaskRun, ctx.run_id)
        task = await s.get(Task, ctx.task_id)
        # 终态提交前最后一次栅栏检查：期间被停止/暂停则按中断收敛
        if run.lease_epoch != ctx.lease_epoch or run.worker_id != ctx.worker_id:
            return
        if task.cancel_generation != ctx.cancel_generation:
            interrupted = "pause" if task.task_status in ("pausing", "paused") else "stop"
        else:
            interrupted = None
            run.run_status = status
            run.finished_time = utcnow()
            task.task_status = status
            task.error_code, task.error_desc = error_code, error_desc
            task.current_stage = None
            extra = list(parts or []) + await _artifact_parts(s, task.task_id, artifact_ids or [])
            await project_task(s, task, task_event="run_finished", detail={"run_id": ctx.run_id},
                               extra_parts=extra, final=True)
    if interrupted:
        await _finish_interrupted(ctx, interrupted)


async def _finish_interrupted(ctx: TaskExecContext, kind: str) -> None:
    from ..db.models import SourceRevision

    async with session_scope() as s:
        run = await s.get(TaskRun, ctx.run_id)
        task = await s.get(Task, ctx.task_id)
        if run.run_status in ("stopped", "paused", "cancelled"):
            return
        run.finished_time = utcnow()
        extra: list[dict] = []
        if kind == "pause" and task.task_status in ("pausing", "paused"):
            run.run_status = "paused"
            task.task_status = "paused"
        else:
            run.run_status = "stopped"
            task.task_status = "stopped"
            # 已提交的来源保留并展示；停止后不再发起新的模型调用
            srcs = (await s.execute(select(SourceRevision).where(
                SourceRevision.task_id == task.task_id, SourceRevision.revision_status == "captured")
                .order_by(SourceRevision.source_no))).scalars().all()
            msg = f"已按你的要求停止。停止前已实际读取 {len(srcs)} 个来源，已保留。"
            extra.append({"type": "text", "part_id": f"stopped-{task.task_id}", "text": msg, "citations": []})
            if srcs:
                extra.append({"type": "source", "part_id": f"sources-{task.task_id}", "task_id": task.task_id,
                              "sources": [{"n": r.source_no, "source_revision_id": r.source_revision_id,
                                           "title": r.title, "url": r.final_url or r.request_url,
                                           "site_name": r.site_name, "retrieved_time": r.retrieved_time.isoformat()}
                                          for r in srcs]})
        task.current_stage = None
        await project_task(s, task, task_event=f"run_{run.run_status}", detail={"run_id": ctx.run_id},
                           extra_parts=extra, final=True)
