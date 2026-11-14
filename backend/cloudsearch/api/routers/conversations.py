from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ...core.ids import new_id, sha256_json, utcnow
from ...db.base import get_session, session_scope
from ...db.models import Conversation, ConversationEvent, Message, MessageTaskRel, Task
from ...orchestrator import control
from ...services.events import (
    conversation_out,
    message_out,
    publish_conversation,
    publish_message,
    subscribe,
    task_out,
    unsubscribe,
)
from ..deps import CurrentUser, current_user, get_conversation
from ..schemas import (
    ConversationIn,
    ConversationList,
    ConversationOut,
    ConversationPatch,
    MessageIn,
    MessageList,
    SendMessageOut,
    StopTurnIn,
    StopTurnOut,
    TaskControlResult,
    TaskOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationIn, u: CurrentUser = Depends(current_user),
                              s: AsyncSession = Depends(get_session)):
    c = Conversation(conversation_id=new_id("conv"), project_id=u.project_id, user_id=u.user_id,
                     title=(body.title or "新对话")[:200])
    s.add(c)
    await s.flush()
    out = await conversation_out(s, c)
    await s.commit()
    return out


@router.get("", response_model=ConversationList)
async def list_conversations(limit: int = Query(30, ge=1, le=100), cursor: str | None = None,
                             q: str | None = None, u: CurrentUser = Depends(current_user),
                             s: AsyncSession = Depends(get_session)):
    stmt = select(Conversation).where(Conversation.project_id == u.project_id, Conversation.user_id == u.user_id,
                                      Conversation.conversation_status == "active")
    if q:
        stmt = stmt.where(Conversation.title.contains(q))
    if cursor:
        stmt = stmt.where(Conversation.conversation_id < cursor)
    rows = (await s.execute(stmt.order_by(Conversation.conversation_id.desc()).limit(limit + 1))).scalars().all()
    items = [await conversation_out(s, c) for c in rows[:limit]]
    items.sort(key=lambda c: c.updated_time, reverse=True)
    return ConversationList(items=items, next_cursor=rows[limit - 1].conversation_id if len(rows) > limit else None)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conv(conversation_id: str, u: CurrentUser = Depends(current_user),
                   s: AsyncSession = Depends(get_session)):
    return await conversation_out(s, await get_conversation(s, u, conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def patch_conv(conversation_id: str, body: ConversationPatch, u: CurrentUser = Depends(current_user),
                     s: AsyncSession = Depends(get_session)):
    c = await get_conversation(s, u, conversation_id)
    if body.title is not None:
        c.title = body.title[:200] or "新对话"
    if body.conversation_status is not None:
        c.conversation_status = body.conversation_status  # 归档不停止任务
    await publish_conversation(s, c)
    out = await conversation_out(s, c)
    await s.commit()
    return out


@router.delete("/{conversation_id}", status_code=204)
async def delete_conv(conversation_id: str, u: CurrentUser = Depends(current_user),
                      s: AsyncSession = Depends(get_session)):
    c = await get_conversation(s, u, conversation_id)
    c.conversation_status = "deleted"  # 软删除墓碑；不级联停止或删除任务
    await s.commit()
    return Response(status_code=204)


@router.get("/{conversation_id}/messages", response_model=MessageList)
async def list_messages(conversation_id: str, u: CurrentUser = Depends(current_user),
                        s: AsyncSession = Depends(get_session)):
    c = await get_conversation(s, u, conversation_id)
    rows = (await s.execute(select(Message).where(Message.conversation_id == conversation_id)
                            .order_by(Message.created_time, Message.role.desc()))).scalars().all()
    return MessageList(items=[await message_out(s, m) for m in rows], last_event_seq_no=c.last_event_seq_no)


@router.post("/{conversation_id}/messages", response_model=SendMessageOut, status_code=202)
async def send_message(conversation_id: str, body: MessageIn, response: Response,
                       u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    c = await get_conversation(s, u, conversation_id)
    body.text = body.text.strip()
    file_ids = list(dict.fromkeys(body.file_ids))
    if not body.text and not file_ids:
        raise HTTPException(422, "消息不能为空")
    req_hash = sha256_json({"text": body.text, "mode": body.mode_selection, "files": file_ids} if file_ids
                           else {"text": body.text, "mode": body.mode_selection})
    # 幂等：同会话同 client_message_id → 返回原消息；内容不同 → 409
    existing = (await s.execute(select(Message).where(Message.conversation_id == conversation_id,
                                                      Message.client_message_id == body.client_message_id))).scalar()
    if existing is not None:
        if existing.request_hash != req_hash:
            raise HTTPException(409, "client_message_id 已用于不同内容")
        reply = (await s.execute(select(Message).where(Message.conversation_id == conversation_id,
                                                       Message.turn_id == existing.turn_id,
                                                       Message.role == "assistant")
                                 .order_by(Message.created_time).limit(1))).scalar()
        response.status_code = 200
        return SendMessageOut(user_message=await message_out(s, existing),
                              assistant_message=await message_out(s, reply), deduplicated=True)
    from ...db.models import UploadedFile
    from ...files.service import file_part

    files = []
    for fid in file_ids:
        f = await s.get(UploadedFile, fid)
        if f is None or f.conversation_id != conversation_id or f.user_id != u.user_id or f.file_status != "active":
            raise HTTPException(422, "附件不存在或不属于这个对话")
        if f.message_id:
            raise HTTPException(409, f"{f.display_name} 已随其他消息发送")
        files.append(f)
    turn_id = new_id("turn")
    now = utcnow()
    text = body.text or "请阅读并总结我上传的文件"
    user_msg = Message(message_id=new_id("msg"), conversation_id=conversation_id, project_id=c.project_id,
                       turn_id=turn_id, role="user", client_message_id=body.client_message_id, request_hash=req_hash,
                       mode_selection=body.mode_selection, message_status="final", created_time=now,
                       parts=[{"type": "text", "part_id": "text", "text": text, "citations": []},
                              *[file_part(f) for f in files]])
    reply = Message(message_id=new_id("msg"), conversation_id=conversation_id, project_id=c.project_id,
                    turn_id=turn_id, role="assistant", message_status="pending", parts=[], created_time=now)
    s.add_all([user_msg, reply])
    for f in files:
        f.message_id = user_msg.message_id
    c.updated_time = now
    await publish_message(s, user_msg, created=True)
    await publish_message(s, reply, created=True)
    out = SendMessageOut(user_message=await message_out(s, user_msg), assistant_message=await message_out(s, reply))
    await s.commit()
    return out


@router.get("/{conversation_id}/events")
async def events(conversation_id: str, request: Request, after: int | None = None,
                 last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
                 u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    await get_conversation(s, u, conversation_id)
    await s.commit()  # 结束鉴权事务并归还连接，长连接期间不占用数据库连接
    cursor = after or 0
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    async def gen():
        nonlocal cursor
        waiter = subscribe(conversation_id)
        try:
            while True:
                if await request.is_disconnected():
                    return
                async with session_scope() as db:
                    rows = (await db.execute(select(ConversationEvent).where(
                        ConversationEvent.conversation_id == conversation_id,
                        ConversationEvent.event_seq_no > cursor).order_by(ConversationEvent.event_seq_no)
                        .limit(200))).scalars().all()
                for r in rows:
                    cursor = r.event_seq_no
                    yield {"id": str(r.event_seq_no), "event": r.event_type,
                           "data": json.dumps(r.event_json, ensure_ascii=False)}
                if not rows:
                    waiter.clear()
                    try:
                        await asyncio.wait_for(waiter.wait(), timeout=1.0)
                    except TimeoutError:
                        pass
        finally:
            unsubscribe(conversation_id, waiter)

    return EventSourceResponse(gen(), ping=15)


@router.get("/{conversation_id}/tasks", response_model=list[TaskOut])
async def conversation_tasks(conversation_id: str, u: CurrentUser = Depends(current_user),
                             s: AsyncSession = Depends(get_session)):
    await get_conversation(s, u, conversation_id)
    rows = (await s.execute(select(Task).where(Task.conversation_id == conversation_id)
                            .order_by(Task.created_time))).scalars().all()
    return [task_out(t) for t in rows]


@router.post("/{conversation_id}/stop-turn", response_model=StopTurnOut)
async def stop_turn(conversation_id: str, body: StopTurnIn, u: CurrentUser = Depends(current_user),
                    s: AsyncSession = Depends(get_session)):
    """停止当前轮：只操作该轮绑定的任务集合，逐项返回结果，不承诺跨任务原子。"""
    await get_conversation(s, u, conversation_id)
    turn_id = body.turn_id
    if turn_id is None:
        turn_id = (await s.execute(select(Message.turn_id).where(
            Message.conversation_id == conversation_id, Message.role == "user")
            .order_by(Message.created_time.desc()).limit(1))).scalar()
    task_ids = (await s.execute(select(MessageTaskRel.task_id).where(
        MessageTaskRel.conversation_id == conversation_id, MessageTaskRel.turn_id == turn_id).distinct())
                ).scalars().all() if turn_id else []
    results = []
    for tid in task_ids:
        t = await s.get(Task, tid)
        if t is None or t.created_by_id != u.user_id:
            results.append(TaskControlResult(task_id=tid, outcome="forbidden"))
            continue
        outcome = await control.stop(s, t)
        results.append(TaskControlResult(task_id=tid, outcome=outcome, task_status=t.task_status))
    await s.commit()
    return StopTurnOut(turn_id=turn_id, results=results)
