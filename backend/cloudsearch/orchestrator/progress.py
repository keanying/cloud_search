"""把任务阶段/计数投影为消息中的 progress 片段，并发布 message_updated / task_updated。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.coordinator import STAGE_LABELS, stages_for
from ..db.base import is_mysql, session_scope
from ..db.models import Task
from ..services.events import publish_message, publish_task, task_output_messages, upsert_part

COUNTER_KEYS = ("queries", "candidates", "sources_read", "sources_failed", "evidence")

# 同一任务的进度更新串行化（读-改-写 JSON 摘要，避免并发读取/抽取时丢失计数）
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def task_stages(t: Task) -> list[str]:
    ds = (t.task_spec or {}).get("dataset") or {}
    return stages_for(t.mode, has_analysis=bool(ds.get("analysis_request")))


def build_progress_part(t: Task) -> dict[str, Any]:
    summary = t.result_summary or {}
    statuses: dict[str, str] = summary.get("stages", {})
    stages = [{"key": k, "label": STAGE_LABELS[k], "status": statuses.get(k, "pending")} for k in task_stages(t)]
    counters = {k: int(summary.get("counters", {}).get(k, 0)) for k in COUNTER_KEYS}
    return {"type": "progress", "part_id": f"progress-{t.task_id}", "task_id": t.task_id,
            "task_status": t.task_status, "stage": t.current_stage,
            "stage_label": STAGE_LABELS.get(t.current_stage or "", ""), "stages": stages, "counters": counters,
            "browser_available": bool(summary.get("browser_available"))}


async def project_task(s: AsyncSession, t: Task, *, task_event: str | None = None,
                       detail: dict | None = None, extra_parts: list[dict] | None = None,
                       final: bool = False) -> None:
    """更新任务绑定的回复消息中的 progress 片段（以及附加片段），并发布事件。"""
    await publish_task(s, t, task_event=task_event, detail=detail)
    for m in await task_output_messages(s, t.task_id):
        parts = m.parts or []
        if any(p.get("part_id") == f"progress-{t.task_id}" for p in parts) or t.task_status != "draft":
            parts = upsert_part(parts, build_progress_part(t))
        for p in extra_parts or []:
            parts = upsert_part(parts, p)
        m.parts = parts
        if final:
            m.message_status = "final"
        await publish_message(s, m)


async def update_progress(task_id: str, *, stage: str | None = None, stage_status: str | None = None,
                          inc: dict[str, int] | None = None, browser_available: bool | None = None,
                          extra_parts: list[dict] | None = None) -> None:
    async with _locks[task_id], session_scope() as s:
        q = select(Task).where(Task.task_id == task_id)
        if is_mysql():
            q = q.with_for_update()  # 跨进程时的行锁
        t = (await s.execute(q)).scalar()
        if t is None:
            return
        summary = dict(t.result_summary or {})
        stages = dict(summary.get("stages", {}))
        counters = dict(summary.get("counters", {}))
        if stage:
            stages[stage] = stage_status or "running"
            if (stage_status or "running") == "running":
                t.current_stage = stage
        for k, v in (inc or {}).items():
            counters[k] = int(counters.get(k, 0)) + v
        if browser_available is not None:
            summary["browser_available"] = browser_available
        summary["stages"], summary["counters"] = stages, counters
        t.result_summary = summary
        await project_task(s, t, extra_parts=extra_parts)
