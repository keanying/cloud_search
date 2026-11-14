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


def message_context(m: Message) -> str:
    """给需求编译看的历史：正文 + 关键数字 + 引用来源（站点/标题），便于理解追问与沿用来源。"""
    text = message_text(m)
    if m.role != "assistant":
        return text
    extra = []
    for p in m.parts or []:
        if p.get("type") == "highlights":
            extra.append("关键数字：" + "；".join(f"{h.get('label')} {h.get('value')}{h.get('unit') or ''}"
                                               for h in p.get("items", [])))
        elif p.get("type") == "source":
            srcs = p.get("sources", [])[:8]
            if srcs:
                extra.append("来源：" + "；".join(
                    f"[{x.get('n')}] {(x.get('title') or '')[:40]}（{x.get('site_name') or ''} {x.get('url', '')}）"
                    for x in srcs))
    return "\n".join([text, *extra]).strip() if text else ""


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
        history = [(m.role, message_context(m)) for m in reversed(history_rows) if message_text(m)]
        pending = (await s.execute(select(Task).where(
            Task.conversation_id == assistant.conversation_id, Task.task_status == "draft")
            .order_by(Task.created_time.desc()).limit(1))).scalar()
        import json

        pending_json = json.dumps(pending.task_spec, ensure_ascii=False) if pending else None
        user_text = message_text(user_msg)
        mode = user_msg.mode_selection or "auto"
        project_id, user_id, conv_id = conv.project_id, conv.user_id, conv.conversation_id
        from ..db.models import UploadedFile
        from ..files.service import describe_for_compiler

        conv_files = (await s.execute(select(UploadedFile).where(
            UploadedFile.conversation_id == conv_id, UploadedFile.file_status == "active",
            UploadedFile.message_id.is_not(None)).order_by(UploadedFile.created_time))).scalars().all()
        attachments = describe_for_compiler(list(conv_files)[-12:])
        usable = {f.file_id for f in conv_files if f.parse_status != "failed"}
        new_files = [f.file_id for f in conv_files if f.message_id == user_msg.message_id]

    try:
        decision = await compile_turn(user_text=user_text, mode_selection=mode, history=history,
                                      pending_spec_json=pending_json, conversation_id=conv_id,
                                      attachments=attachments, new_file_ids=new_files)
        decision = apply_file_rules(decision, user_text=user_text, usable=usable,
                                    new_files=[f for f in new_files if f in usable], mode=mode)
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


def apply_file_rules(decision, *, user_text: str, usable: set[str], new_files: list[str], mode: str):
    """附件的确定性规则：只引用本对话里可用的文件；本条消息带了文件却被判为闲聊时，改为基于文件回答。"""
    from ..contracts import Scope, TaskSpec

    if decision.kind == "task" and decision.task_spec is not None:
        sc = decision.task_spec.scope
        sc.file_ids = [f for f in dict.fromkeys(sc.file_ids) if f in usable]
        if not sc.file_ids and new_files:
            sc.file_ids = list(new_files)
        return decision
    if decision.kind == "chat" and new_files:
        title = (user_text or "文件问答")[:40]
        decision.kind = "task"
        decision.task_spec = TaskSpec(
            mode=mode if mode in ("quick_search", "research") else "quick_search", title=title,
            requirement_text=user_text or "阅读并总结上传的文件",
            scope=Scope(questions=[user_text or "这些文件的主要内容是什么？"], file_ids=list(new_files)))
        decision.needs_confirmation = False
        decision.plan_steps = decision.plan_steps or ["读取并解析文件", "找出与问题相关的内容", "核对原文出处", "给出带出处的回答"]
        decision.reply = "好的，我先读一下你上传的文件。"
    return decision


async def _fail(message_id: str, code: str, text: str) -> None:
    async with session_scope() as s:
        m = await s.get(Message, message_id)
        if m is None:
            return
        m.parts = [{"type": "error", "part_id": "error", "code": code, "message": text}]
        m.message_status = "error"
        m.lease_expire_time = None
        await publish_message(s, m)
