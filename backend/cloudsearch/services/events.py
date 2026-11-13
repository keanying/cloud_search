"""事件与投影：状态变更与事件在同一事务写入；SSE 按会话 event_seq_no 补齐。

消息中的 progress/plan_summary 片段是任务状态的展示投影，不是任务状态源。
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.schemas import ConversationOut, MessageOut, TaskOut
from ..db.models import Conversation, ConversationEvent, Message, MessageTaskRel, Task, TaskEvent

# 进程内唤醒：同进程的 SSE 连接在新事件写入后立即推送（跨进程依赖轮询兜底）
_waiters: dict[str, set[asyncio.Event]] = {}


def subscribe(conversation_id: str) -> asyncio.Event:
    ev = asyncio.Event()
    _waiters.setdefault(conversation_id, set()).add(ev)
    return ev


def unsubscribe(conversation_id: str, ev: asyncio.Event) -> None:
    _waiters.get(conversation_id, set()).discard(ev)


def _notify(conversation_id: str) -> None:
    for ev in list(_waiters.get(conversation_id, ())):
        ev.set()


async def append_conversation_event(s: AsyncSession, conversation_id: str, event_type: str,
                                    data: dict[str, Any]) -> int:
    await s.execute(update(Conversation).where(Conversation.conversation_id == conversation_id)
                    .values(last_event_seq_no=Conversation.last_event_seq_no + 1))
    seq = (await s.execute(select(Conversation.last_event_seq_no)
                           .where(Conversation.conversation_id == conversation_id))).scalar_one()
    s.add(ConversationEvent(conversation_id=conversation_id, event_seq_no=seq, event_type=event_type,
                            event_json=data))
    # 提交后再唤醒（调用方事务提交前唤醒会导致读取不到；SSE 轮询会兜底）
    asyncio.get_running_loop().call_later(0.05, _notify, conversation_id)
    return seq


async def append_task_event(s: AsyncSession, task_id: str, event_type: str, data: dict[str, Any]) -> None:
    seq = (await s.execute(select(func.coalesce(func.max(TaskEvent.event_seq_no), 0))
                           .where(TaskEvent.task_id == task_id))).scalar_one() + 1
    s.add(TaskEvent(task_id=task_id, event_seq_no=seq, event_type=event_type, event_json=data))


# ---------------------------------------------------------------- 序列化
async def message_task_ids(s: AsyncSession, message_id: str) -> list[str]:
    rows = await s.execute(select(MessageTaskRel.task_id).where(MessageTaskRel.message_id == message_id).distinct())
    return [r[0] for r in rows]


async def message_out(s: AsyncSession, m: Message) -> MessageOut:
    return MessageOut(message_id=m.message_id, conversation_id=m.conversation_id, turn_id=m.turn_id,
                      role=m.role, parts=m.parts or [], message_status=m.message_status,
                      mode_selection=m.mode_selection, task_ids=await message_task_ids(s, m.message_id),
                      created_time=m.created_time, updated_time=m.updated_time)


def task_out(t: Task) -> TaskOut:
    return TaskOut(task_id=t.task_id, conversation_id=t.conversation_id, parent_task_id=t.parent_task_id,
                   mode=t.mode, title=t.title, task_status=t.task_status, status_reason=t.status_reason,
                   current_stage=t.current_stage, cancel_generation=t.cancel_generation, plan_hash=t.plan_hash,
                   task_spec=t.task_spec, result_summary=t.result_summary, error_code=t.error_code,
                   error_desc=t.error_desc, llm_request_qty=t.llm_request_qty, spent_minor_amt=t.spent_minor_amt,
                   cost_unknown_qty=t.cost_unknown_qty, created_time=t.created_time, updated_time=t.updated_time)


ACTIVE_STATUSES = ("queued", "running", "pausing", "stopping")


async def conversation_out(s: AsyncSession, c: Conversation) -> ConversationOut:
    active = (await s.execute(select(func.count()).select_from(Task).where(
        Task.conversation_id == c.conversation_id, Task.task_status.in_(ACTIVE_STATUSES)))).scalar_one()
    return ConversationOut(conversation_id=c.conversation_id, title=c.title,
                           conversation_status=c.conversation_status, last_event_seq_no=c.last_event_seq_no,
                           active_task_qty=active, created_time=c.created_time, updated_time=c.updated_time)


# ---------------------------------------------------------------- 常用发布
async def publish_message(s: AsyncSession, m: Message, *, created: bool = False) -> None:
    await s.flush()
    out = await message_out(s, m)
    await append_conversation_event(s, m.conversation_id, "message_created" if created else "message_updated",
                                    out.model_dump(mode="json"))


async def publish_task(s: AsyncSession, t: Task, *, task_event: str | None = None,
                       detail: dict[str, Any] | None = None) -> None:
    await s.flush()
    if task_event:
        await append_task_event(s, t.task_id, task_event, {"task_status": t.task_status, **(detail or {})})
    if t.conversation_id:
        await append_conversation_event(s, t.conversation_id, "task_updated", task_out(t).model_dump(mode="json"))


async def publish_conversation(s: AsyncSession, c: Conversation) -> None:
    await s.flush()
    out = await conversation_out(s, c)
    await append_conversation_event(s, c.conversation_id, "conversation_updated", out.model_dump(mode="json"))


async def task_output_messages(s: AsyncSession, task_id: str) -> list[Message]:
    rows = await s.execute(select(Message).join(MessageTaskRel, MessageTaskRel.message_id == Message.message_id)
                           .where(MessageTaskRel.task_id == task_id, MessageTaskRel.binding_type == "output"))
    return list(rows.scalars().all())


def upsert_part(parts: list[dict], part: dict, *, key: str = "part_id") -> list[dict]:
    """按 part_id 替换片段；不存在则追加。返回新列表（触发 JSON 列变更检测）。"""
    out = [dict(p) for p in parts]
    for i, p in enumerate(out):
        if p.get(key) == part.get(key):
            out[i] = part
            return out
    out.append(part)
    return out
