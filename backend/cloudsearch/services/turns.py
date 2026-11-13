"""处理一轮对话：需求编译 → 直接答复 / 澄清 / 创建任务（按政策自动开始或等待确认）。"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import and_, or_, select

from ..agents.requirement_compiler import compile_turn
from ..core.ids import utcnow
from ..db.base import is_mysql, session_scope
from ..db.models import Conversation, Message, Task
from ..llm.registry import LlmNotConfigured
from ..orchestrator import control
from ..orchestrator.progress import project_task
from .events import publish_conversation, publish_message

log = logging.getLogger(__name__)

TURN_LEASE_S = 180


def message_text(m: Message) -> str:
    return "\n".join(p.get("text", "") for p in (m.parts or []) if p.get("type") == "text").strip()


async def claim_turn(worker_id: str) -> str | None:
    now = utcnow()
    async with session_scope() as s:
        q = (select(Message).where(Message.role == "assistant", or_(
            Message.message_status == "pending",
            and_(Message.message_status == "processing", Message.lease_expire_time < now)))
             .order_by(Message.created_time).limit(1))
        if is_mysql():
            q = q.with_for_update(skip_locked=True)
        m = (await s.execute(q)).scalar()
        if m is None:
            return None
        m.message_status = "processing"
        m.worker_id = worker_id
        m.lease_expire_time = now + timedelta(seconds=TURN_LEASE_S)
        return m.message_id


async def process_turn(message_id: str, worker_id: str) -> None:
    async with session_scope() as s:
        assistant = await s.get(Message, message_id)
        if assistant is None or assistant.worker_id != worker_id:
            return
        conv = await s.get(Conversation, assistant.conversation_id)
        user_msg = (await s.execute(select(Message).where(
            Message.conversation_id == assistant.conversation_id, Message.turn_id == assistant.turn_id,
            Message.role == "user"))).scalar()
        history_rows = (await s.execute(select(Message).where(
            Message.conversation_id == assistant.conversation_id, Message.created_time < user_msg.created_time,
            Message.message_status == "final").order_by(Message.created_time.desc()).limit(12))).scalars().all()
        history = [(m.role, message_text(m)) for m in reversed(history_rows) if message_text(m)]
        pending = (await s.execute(select(Task).where(
            Task.conversation_id == assistant.conversation_id, Task.task_status == "draft")
            .order_by(Task.created_time.desc()).limit(1))).scalar()
        import json

        pending_json = json.dumps(pending.task_spec, ensure_ascii=False) if pending else None
        user_text = message_text(user_msg)
        mode = user_msg.mode_selection or "auto"
        project_id, user_id, conv_id = conv.project_id, conv.user_id, conv.conversation_id

    try:
        decision = await compile_turn(user_text=user_text, mode_selection=mode, history=history,
                                      pending_spec_json=pending_json, conversation_id=conv_id)
    except LlmNotConfigured as e:
        await _fail(message_id, "llm_not_configured", f"{e}。管理员配置后重新发送即可。")
        return
    except Exception as e:  # noqa: BLE001
        log.exception("turn %s failed", message_id)
        await _fail(message_id, type(e).__name__, f"理解需求时调用模型失败（{type(e).__name__}），请稍后重试。")
        return

    async with session_scope() as s:
        assistant = await s.get(Message, message_id)
        if assistant.worker_id != worker_id:
            return
        conv = await s.get(Conversation, conv_id)
        parts: list[dict] = [{"type": "text", "part_id": "reply", "text": decision.reply, "citations": []}]
        if decision.kind == "clarify" and decision.questions:
            parts.append({"type": "clarification", "part_id": "clarify", "questions": decision.questions[:4]})
        assistant.parts = parts
        task = None
        if decision.kind == "task" and decision.task_spec is not None:
            if pending is not None:
                old = await s.get(Task, pending.task_id)
                if old and old.task_status == "draft":
                    await control.stop(s, old)  # 被新计划替代
            task = await control.create_task(
                s, project_id=project_id, user_id=user_id, conversation_id=conv_id, turn_id=assistant.turn_id,
                user_message_id=user_msg.message_id, assistant=assistant, spec=decision.task_spec,
                plan_steps=decision.plan_steps, auto_start=not decision.needs_confirmation)
        assistant.message_status = "final"
        assistant.lease_expire_time = None
        if decision.conversation_title and conv.title in ("新对话", ""):
            conv.title = decision.conversation_title[:60]
            await publish_conversation(s, conv)
        conv.updated_time = utcnow()
        await publish_message(s, assistant)
        if task is not None:
            await project_task(s, task, task_event="created")


async def _fail(message_id: str, code: str, text: str) -> None:
    async with session_scope() as s:
        m = await s.get(Message, message_id)
        if m is None:
            return
        m.parts = [{"type": "error", "part_id": "error", "code": code, "message": text}]
        m.message_status = "error"
        m.lease_expire_time = None
        await publish_message(s, m)
