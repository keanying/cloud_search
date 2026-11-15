"""把任务阶段/计数投影为消息中的 progress 片段，并发布 message_updated / task_updated。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.coordinator import STAGE_LABELS, stages_for_spec
from ..db.base import is_mysql, session_scope
from ..core.ids import utcnow
from ..db.models import Task
from ..services.events import publish_message, publish_task, task_output_messages, upsert_part

# 与 control.TERMINAL 一致（control 引用了本模块，这里不反向引用）
TERMINAL = ("stopped", "completed", "partial_failed", "failed", "cancelled")

COUNTER_KEYS = ("queries", "candidates", "sources_read", "sources_failed", "evidence")

# 同一任务的进度更新串行化（读-改-写 JSON 摘要，避免并发读取/抽取时丢失计数）
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def task_stages(t: Task) -> list[str]:
    return stages_for_spec({**(t.task_spec or {}), "mode": t.mode})


def _now_ms() -> int:
    return int(utcnow().timestamp() * 1000)


def timing_of(summary: dict) -> dict[str, Any]:
    """耗时：任务开始/结束时间、总耗时、各阶段累计耗时（进行中的阶段按当前时间计）。"""
    tm = summary.get("timing") or {}
    now = _now_ms()
    stage_ms = dict(tm.get("stage_ms") or {})
    for k, start in (tm.get("open") or {}).items():
        stage_ms[k] = stage_ms.get(k, 0) + max(0, now - start)
    started, finished = tm.get("started_ms"), tm.get("finished_ms")
    total = (finished or now) - started if started else None
    return {"started_ms": started, "finished_ms": finished, "elapsed_ms": total, "stage_ms": stage_ms}


def build_progress_part(t: Task) -> dict[str, Any]:
    summary = t.result_summary or {}
    statuses: dict[str, str] = summary.get("stages", {})
    timing = timing_of(summary)
    stages = [{"key": k, "label": STAGE_LABELS[k], "status": statuses.get(k, "pending"),
               "elapsed_ms": timing["stage_ms"].get(k)} for k in task_stages(t)]
    counters = {k: int(summary.get("counters", {}).get(k, 0)) for k in COUNTER_KEYS}
    return {"type": "progress", "part_id": f"progress-{t.task_id}", "task_id": t.task_id,
            "task_status": t.task_status, "stage": t.current_stage,
            "stage_label": STAGE_LABELS.get(t.current_stage or "", ""), "stages": stages, "counters": counters,
            # 浏览器只在搜索/读网页阶段可看；任务结束（含失败、停止）后一律关闭入口
            "browser_available": bool(summary.get("browser_available")) and t.task_status not in TERMINAL,
            "metrics": {"started_ms": timing["started_ms"], "finished_ms": timing["finished_ms"],
                        "elapsed_ms": timing["elapsed_ms"], "llm_requests": t.llm_request_qty,
                        "spent_minor_amt": t.spent_minor_amt, "cost_unknown_qty": t.cost_unknown_qty}}


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
        if final:  # 撰写过程中的实时草稿由最终成果替代
            parts = [p for p in parts if p.get("type") != "draft"]
        m.parts = parts
        if final:
            m.message_status = "final"
        await publish_message(s, m)


def close_timing(summary: dict) -> dict:
    """任务结束：收尾所有进行中的阶段并记录结束时间。"""
    tm = dict(summary.get("timing") or {})
    now = _now_ms()
    stage_ms = dict(tm.get("stage_ms") or {})
    for k, start in (tm.get("open") or {}).items():
        stage_ms[k] = stage_ms.get(k, 0) + max(0, now - start)
    tm.update({"open": {}, "stage_ms": stage_ms, "finished_ms": now})
    tm.setdefault("started_ms", now)
    return {**summary, "timing": tm}


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
            st = stage_status or "running"
            stages[stage] = st
            if st == "running":
                t.current_stage = stage
            tm = dict(summary.get("timing") or {})
            opened, stage_ms = dict(tm.get("open") or {}), dict(tm.get("stage_ms") or {})
            now = _now_ms()
            tm.setdefault("started_ms", now)
            if st == "running":
                opened.setdefault(stage, now)  # 同一阶段多轮（如补查）累计
            elif stage in opened:
                stage_ms[stage] = stage_ms.get(stage, 0) + max(0, now - opened.pop(stage))
            tm["open"], tm["stage_ms"] = opened, stage_ms
            summary["timing"] = tm
        for k, v in (inc or {}).items():
            counters[k] = int(counters.get(k, 0)) + v
        if browser_available is not None:
            summary["browser_available"] = browser_available
        summary["stages"], summary["counters"] = stages, counters
        t.result_summary = summary
        await project_task(s, t, extra_parts=extra_parts)
