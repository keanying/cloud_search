"""任务控制命令（API 侧，短事务 + 事件同提交）。

- confirm：绑定精确 plan_hash；计划改动后旧确认失效
- stop：递增 cancel_generation（执行中的 worker 在下一个栅栏点停止，迟到结果被隔离）；未执行的直接 cancelled
- pause/resume：pausing→paused；恢复为同 task 新 run，复用已成功节点
- continue：终态任务续做为新 task + parent_task_id，旧产物不变
关闭阅览、刷新页面、切换对话都不会调用这里。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..contracts import MODE_LABELS, TaskSpec
from ..core.ids import new_id, sha256_json
from ..db.models import Message, MessageTaskRel, Task, TaskRun
from ..services.events import upsert_part
from .progress import project_task

TERMINAL = ("stopped", "completed", "partial_failed", "failed", "cancelled")


class ControlError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def plan_part(t: Task, spec: TaskSpec, steps: list[str], status: str) -> dict:
    fields = [{"key": f.key, "label": f.label, "type": f.type, "required": f.required}
              for f in (spec.dataset.fields if spec.dataset else [])]
    scope = spec.scope
    summary_bits = [MODE_LABELS[spec.mode]]
    if scope.items:
        summary_bits.append("对象：" + "、".join(scope.items[:8]))
    if scope.region:
        summary_bits.append(f"地域：{scope.region}")
    if scope.time_range:
        summary_bits.append(f"时间：{scope.time_range}")
    if spec.dataset:
        summary_bits.append(f"每行：{spec.dataset.entity}，最多 {spec.dataset.max_records} 行")
    return {"type": "plan_summary", "part_id": f"plan-{t.task_id}", "task_id": t.task_id, "mode": spec.mode,
            "title": spec.title, "summary": "；".join(summary_bits), "steps": steps,
            "limits": {"max_queries": spec.limits.max_queries, "max_sources": spec.limits.max_sources},
            "fields": fields, "plan_hash": t.plan_hash, "status": status}


async def _new_run(s: AsyncSession, t: Task, resume_from: str | None = None) -> TaskRun:
    seq = (await s.execute(select(func.coalesce(func.max(TaskRun.run_seq_no), 0))
                           .where(TaskRun.task_id == t.task_id))).scalar_one() + 1
    run = TaskRun(run_id=new_id("run"), task_id=t.task_id, project_id=t.project_id, run_seq_no=seq,
                  run_status="queued", cancel_generation=t.cancel_generation, plan_hash=t.plan_hash,
                  resume_from_run_id=resume_from)
    s.add(run)
    return run


async def create_task(s: AsyncSession, *, project_id: str, user_id: str, conversation_id: str, turn_id: str,
                      user_message_id: str, assistant: Message, spec: TaskSpec, plan_steps: list[str],
                      auto_start: bool, parent_task_id: str | None = None) -> Task:
    t = Task(task_id=new_id("task"), project_id=project_id, created_by_id=user_id, conversation_id=conversation_id,
             parent_task_id=parent_task_id, mode=spec.mode, title=spec.title[:200],
             task_spec=spec.model_dump(mode="json"), plan_hash=sha256_json(spec.model_dump(mode="json")),
             task_status="queued" if auto_start else "draft", status_reason=None if auto_start else "approval",
             result_summary={"stages": {}, "counters": {}, "plan_steps": plan_steps})
    s.add(t)
    s.add(MessageTaskRel(message_id=user_message_id, task_id=t.task_id, binding_type="request",
                         conversation_id=conversation_id, turn_id=turn_id))
    s.add(MessageTaskRel(message_id=assistant.message_id, task_id=t.task_id, binding_type="output",
                         conversation_id=conversation_id, turn_id=turn_id))
    assistant.parts = upsert_part(assistant.parts or [],
                                  plan_part(t, spec, plan_steps, "auto_started" if auto_start else "awaiting_confirmation"))
    if auto_start:
        await _new_run(s, t)
    await s.flush()
    return t


async def _set_plan_status(s: AsyncSession, t: Task, status: str) -> None:
    rows = (await s.execute(select(Message).join(MessageTaskRel, MessageTaskRel.message_id == Message.message_id)
                            .where(MessageTaskRel.task_id == t.task_id,
                                   MessageTaskRel.binding_type == "output"))).scalars().all()
    for m in rows:
        parts = []
        for p in m.parts or []:
            if p.get("part_id") == f"plan-{t.task_id}":
                p = {**p, "status": status}
            parts.append(p)
        m.parts = parts


async def confirm(s: AsyncSession, t: Task, plan_hash: str) -> Task:
    if t.task_status != "draft":
        raise ControlError("not_draft", "该计划已确认或已不可确认")
    if plan_hash != t.plan_hash:
        raise ControlError("plan_changed", "计划已变化，请确认最新计划", 412)
    t.task_status, t.status_reason = "queued", None
    await _new_run(s, t)
    await _set_plan_status(s, t, "confirmed")
    await project_task(s, t, task_event="confirmed")
    return t


async def stop(s: AsyncSession, t: Task) -> str:
    """返回 outcome：accepted / not_needed。"""
    if t.task_status in TERMINAL:
        return "not_needed"
    t.cancel_generation += 1
    if t.task_status in ("draft", "ready", "queued", "paused"):
        # 尚未执行（或已暂停无在途动作）：直接收敛
        t.task_status = "cancelled" if t.task_status in ("draft", "ready", "queued") else "stopped"
        runs = (await s.execute(select(TaskRun).where(TaskRun.task_id == t.task_id,
                                                      TaskRun.run_status.in_(("queued", "paused"))))).scalars().all()
        for r in runs:
            r.run_status = "cancelled"
        if t.status_reason == "approval":
            await _set_plan_status(s, t, "cancelled")
        t.current_stage = None
    else:
        t.task_status = "stopping"
    await project_task(s, t, task_event="stop_requested")
    return "accepted"


async def pause(s: AsyncSession, t: Task) -> Task:
    if t.task_status not in ("queued", "running"):
        raise ControlError("not_running", "只有排队或执行中的任务可以暂停")
    t.cancel_generation += 1
    if t.task_status == "queued":
        t.task_status = "paused"
        for r in (await s.execute(select(TaskRun).where(TaskRun.task_id == t.task_id,
                                                         TaskRun.run_status == "queued"))).scalars():
            r.run_status = "paused"
    else:
        t.task_status = "pausing"
    await project_task(s, t, task_event="pause_requested")
    return t


async def resume(s: AsyncSession, t: Task) -> Task:
    if t.task_status != "paused":
        raise ControlError("not_paused", "只有已暂停的任务可以继续")
    last = (await s.execute(select(TaskRun).where(TaskRun.task_id == t.task_id)
                            .order_by(TaskRun.run_seq_no.desc()).limit(1))).scalar()
    t.task_status = "queued"
    await _new_run(s, t, resume_from=last.run_id if last else None)
    await project_task(s, t, task_event="resumed")
    return t


async def continue_as_new(s: AsyncSession, t: Task, *, user_id: str) -> Task:
    """终态续做：新 task 引用 parent_task_id，重新确认后执行；旧产物冻结。"""
    if t.task_status not in TERMINAL:
        raise ControlError("not_terminal", "任务尚未结束，可以暂停/继续而无需新建")
    spec = TaskSpec.model_validate(t.task_spec)
    out_msgs = (await s.execute(select(Message).join(MessageTaskRel, MessageTaskRel.message_id == Message.message_id)
                                .where(MessageTaskRel.task_id == t.task_id))).scalars().all()
    user_msg = next((m for m in out_msgs if m.role == "user"), None)
    turn_id = user_msg.turn_id if user_msg else new_id("turn")
    assistant = Message(message_id=new_id("msg"), conversation_id=t.conversation_id, project_id=t.project_id,
                        turn_id=turn_id, role="assistant", message_status="final",
                        parts=[{"type": "text", "part_id": "intro", "citations": [],
                                "text": f"继续「{spec.title}」：这是一个新任务，会重新搜索并读取来源，之前的成果文件保持不变。"}])
    s.add(assistant)
    await s.flush()
    from ..services.events import publish_message

    new = await create_task(s, project_id=t.project_id, user_id=user_id, conversation_id=t.conversation_id,
                            turn_id=turn_id, user_message_id=user_msg.message_id if user_msg else assistant.message_id,
                            assistant=assistant, spec=spec,
                            plan_steps=(t.result_summary or {}).get("plan_steps", []), auto_start=False,
                            parent_task_id=t.task_id)
    await publish_message(s, assistant, created=True)
    await project_task(s, new, task_event="created", detail={"parent_task_id": t.task_id})
    return new
