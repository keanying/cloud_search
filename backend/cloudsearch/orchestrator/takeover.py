"""人工接管编排：遇到人机验证/登录墙时暂停当前浏览动作，请用户在实时画面中处理。

状态（src_opr_browser_session_f.handoff_state）：
  requested → (用户点“接手处理”) active → (用户点“完成”) resolved / (“跳过”) skipped；无人处理超时 → timeout
等待期间：AI 不对该页面做任何动作；每秒检查任务栅栏（停止/暂停立即结束等待）；接管期间画面不落盘。
控制命令通过数据库传递，因此 API 与 worker 不在同一进程时同样有效。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from ..browser import live
from ..core.config import get_settings
from ..core.ids import iso, new_id, utcnow
from ..db.base import session_scope
from ..db.models import BrowserSession, Task
from .context import TaskExecContext
from .progress import project_task

log = logging.getLogger(__name__)

FINAL = ("resolved", "skipped", "timeout")


def takeover_part(part_id: str, task_id: str, bsid: str, reason: str, state: str, deadline) -> dict:
    return {"type": "takeover", "part_id": part_id, "task_id": task_id, "browser_session_id": bsid,
            "reason": reason, "state": state, "deadline_time": iso(deadline)}


async def _publish(task_id: str, part: dict, event: str) -> None:
    async with session_scope() as db:
        t = await db.get(Task, task_id)
        if t is not None:
            await project_task(db, t, task_event=event, detail={"browser_session_id": part["browser_session_id"]},
                               extra_parts=[part])


async def request_takeover(ctx: TaskExecContext, browser_session_id: str, reason: str) -> bool:
    """请求人工接管并等待结果；返回 True 表示用户已处理完成（调用方应重试刚才的动作）。"""
    from ..core.tracelog import trace

    s = get_settings()
    if not s.browser_takeover_enabled:
        trace("takeover", "需要人工处理，但已关闭“请用户接手”（browser.takeover_enabled），直接跳过", reason=reason)
        return False
    trace("takeover", "请求用户接手处理", reason=reason, timeout_s=s.browser_takeover_timeout_s)
    deadline = utcnow() + timedelta(seconds=s.browser_takeover_timeout_s)
    part_id = f"takeover-{new_id('h')}"
    async with session_scope() as db:
        row = await db.get(BrowserSession, browser_session_id)
        if row is None or row.session_status != "active":
            return False
        row.handoff_state, row.handoff_reason, row.handoff_deadline, row.handoff_user_id = (
            "requested", reason[:256], deadline, None)
    await _publish(ctx.task_id, takeover_part(part_id, ctx.task_id, browser_session_id, reason, "requested", deadline),
                   "takeover_requested")
    ch = live.CHANNELS.get(browser_session_id)
    if ch is not None:
        ch.handoff_active = True
    log.info("takeover requested for %s: %s", browser_session_id, reason)
    outcome = "timeout"
    try:
        last_state = "requested"
        while True:
            await asyncio.sleep(1.0)
            await ctx.check()  # 任务被停止/暂停 → 抛出，结束等待
            async with session_scope() as db:
                row = await db.get(BrowserSession, browser_session_id)
                state, dl = row.handoff_state, row.handoff_deadline
            if state in FINAL:
                outcome = state
                break
            if state != last_state:  # requested → active：卡片状态同步
                await _publish(ctx.task_id, takeover_part(part_id, ctx.task_id, browser_session_id, reason, state, dl),
                               f"takeover_{state}")
                last_state = state
            if dl is not None and utcnow() > dl:
                outcome = "timeout"
                break
    except BaseException:
        outcome = "skipped"
        raise
    finally:
        if ch is not None:
            ch.handoff_active = False
        async with session_scope() as db:
            row = await db.get(BrowserSession, browser_session_id)
            if row is not None:
                row.handoff_state, row.handoff_user_id = outcome, None
        await asyncio.shield(_publish(ctx.task_id, takeover_part(part_id, ctx.task_id, browser_session_id, reason,
                                                                 outcome, deadline), f"takeover_{outcome}"))
        log.info("takeover %s for %s", outcome, browser_session_id)
    trace("takeover", f"接手结果：{ {'resolved': '用户已完成', 'skipped': '用户选择跳过', 'timeout': '等待超时'}.get(outcome, outcome) }")
    return outcome == "resolved"
