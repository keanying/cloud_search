"""右侧阅览：定期截图（只读）、实时画面（CDP 推流）与人工接管。

- 只读接口不含任何导航/点击参数；查看本身不会创建会话或导航。
- 实时画面通过 WebSocket，需先用登录态换取 60 秒有效的一次性票据（浏览器 WebSocket 无法携带认证头）。
- 只有任务所有者可以接管；接管仅在系统请求（handoff_state=requested）时开放，输入只在 active 且为本人时生效。
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from ...browser import live
from ...browser.live_server import internal_signature, serve_channel
from ...core.config import get_settings
from ...core.ids import utcnow
from ...core.storage import get_storage
from ...db.base import get_session, session_scope
from ...db.models import BrowserSession, Task
from ..deps import CurrentUser, current_user
from ..schemas import LiveTicketOut, TakeoverReturnIn, ViewerMetaOut

router = APIRouter(prefix="/browser-sessions", tags=["viewer"])

TICKET_TTL_S = 60


async def _session(s: AsyncSession, u: CurrentUser, bsid: str) -> tuple[BrowserSession, Task]:
    bs = await s.get(BrowserSession, bsid)
    task = await s.get(Task, bs.task_id) if bs else None
    if bs is None or task is None or bs.project_id != u.project_id or (
            task.created_by_id != u.user_id and not u.is_admin):
        raise HTTPException(404, "阅览会话不存在或无权限")
    return bs, task


def live_available(bs: BrowserSession) -> bool:
    return bs.session_status == "active" and (bs.browser_session_id in live.CHANNELS or bool(bs.live_endpoint))


def meta_out(bs: BrowserSession, task: Task) -> ViewerMetaOut:
    active = bs.session_status == "active"
    stale_after = timedelta(seconds=get_settings().browser_frame_interval_s * 3 + 10)
    stale = bs.frame_time is None or (active and utcnow() - bs.frame_time > stale_after) or not active
    return ViewerMetaOut(browser_session_id=bs.browser_session_id, task_id=bs.task_id, session_label=bs.session_label,
                         session_status=bs.session_status, current_url=bs.current_url, current_title=bs.current_title,
                         current_activity=bs.current_activity, frame_seq_no=bs.frame_seq_no, frame_time=bs.frame_time,
                         connected=active, stale=stale, masked=bs.frame_masked, task_status=task.task_status,
                         live_available=live_available(bs), handoff_state=bs.handoff_state,
                         handoff_reason=bs.handoff_reason, handoff_deadline=bs.handoff_deadline)


@router.get("/{browser_session_id}/viewer-meta", response_model=ViewerMetaOut)
async def viewer_meta(browser_session_id: str, u: CurrentUser = Depends(current_user),
                      s: AsyncSession = Depends(get_session)):
    return meta_out(*await _session(s, u, browser_session_id))


@router.get("/{browser_session_id}/viewer-snapshot")
async def viewer_snapshot(browser_session_id: str, u: CurrentUser = Depends(current_user),
                          s: AsyncSession = Depends(get_session)):
    bs, _ = await _session(s, u, browser_session_id)
    if bs.frame_masked or not bs.frame_ref:
        raise HTTPException(404, "暂无可显示的画面")
    data = await get_storage().get(bs.frame_ref)
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store", "X-Frame-Seq": str(bs.frame_seq_no)})


# ---------------------------------------------------------------- 实时画面
@router.post("/{browser_session_id}/live-ticket", response_model=LiveTicketOut)
async def live_ticket(browser_session_id: str, u: CurrentUser = Depends(current_user),
                      s: AsyncSession = Depends(get_session)):
    bs, _ = await _session(s, u, browser_session_id)
    if not live_available(bs):
        raise HTTPException(409, "该会话暂不支持实时画面（已结束或执行器未开放实时通道）")
    now = utcnow()
    ticket = jwt.encode({"typ": "live", "bs": browser_session_id, "sub": u.user_id, "iat": now,
                         "exp": now + timedelta(seconds=TICKET_TTL_S)}, get_settings().secret_key, algorithm="HS256")
    return LiveTicketOut(ticket=ticket, expires_in=TICKET_TTL_S,
                         interactive=bs.handoff_state == "active" and bs.handoff_user_id == u.user_id)


@router.websocket("/{browser_session_id}/live")
async def live_ws(ws: WebSocket, browser_session_id: str, ticket: str):
    try:
        claims = jwt.decode(ticket, get_settings().secret_key, algorithms=["HS256"])
        if claims.get("typ") != "live" or claims.get("bs") != browser_session_id:
            raise jwt.InvalidTokenError()
    except jwt.PyJWTError:
        await ws.close(code=4401)
        return
    user_id = claims["sub"]
    async with session_scope() as db:
        bs = await db.get(BrowserSession, browser_session_id)
        endpoint = bs.live_endpoint if bs else None
    await ws.accept()
    if browser_session_id in live.CHANNELS:  # 嵌入模式：浏览器就在本进程
        await serve_channel(ws, browser_session_id, user_id)
        return
    if not endpoint:
        await ws.send_json({"type": "error", "message": "云端浏览器会话不在线"})
        await ws.close()
        return
    await _relay(ws, f"{endpoint}/internal/live/{browser_session_id}?uid={user_id}"
                     f"&sig={internal_signature(browser_session_id, user_id)}")


async def _relay(ws: WebSocket, url: str) -> None:
    """多进程部署：把前端 WebSocket 与 worker 内部通道双向转发。"""
    import websockets

    try:
        async with websockets.connect(url, max_size=None, open_timeout=10) as up:
            async def down():
                async for m in up:
                    await ws.send_text(m if isinstance(m, str) else m.decode())

            async def upstream():
                while True:
                    await up.send(await ws.receive_text())

            tasks = [asyncio.create_task(down()), asyncio.create_task(upstream())]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in tasks:
                t.cancel()
    except Exception:  # noqa: BLE001
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "error", "message": "实时通道连接失败"})
    finally:
        with contextlib.suppress(Exception):
            await ws.close()


# ---------------------------------------------------------------- 人工接管
@router.post("/{browser_session_id}/takeover", response_model=ViewerMetaOut)
async def takeover(browser_session_id: str, u: CurrentUser = Depends(current_user),
                   s: AsyncSession = Depends(get_session)):
    bs, task = await _session(s, u, browser_session_id)
    if task.created_by_id != u.user_id:
        raise HTTPException(403, "只有任务发起人可以接手处理")
    if bs.handoff_state not in ("requested", "active"):
        raise HTTPException(409, "当前不需要人工处理")
    if bs.handoff_state == "active" and bs.handoff_user_id != u.user_id:
        raise HTTPException(409, "已有其他人正在处理")
    bs.handoff_state, bs.handoff_user_id = "active", u.user_id
    # 接手后给足操作时间
    bs.handoff_deadline = utcnow() + timedelta(seconds=get_settings().browser_takeover_timeout_s)
    out = meta_out(bs, task)
    await s.commit()
    return out


@router.post("/{browser_session_id}/takeover/return", response_model=ViewerMetaOut)
async def takeover_return(browser_session_id: str, body: TakeoverReturnIn, u: CurrentUser = Depends(current_user),
                          s: AsyncSession = Depends(get_session)):
    bs, task = await _session(s, u, browser_session_id)
    if task.created_by_id != u.user_id:
        raise HTTPException(403, "只有任务发起人可以操作")
    if bs.handoff_state not in ("requested", "active"):
        raise HTTPException(409, "当前没有进行中的人工处理")
    bs.handoff_state = "resolved" if body.resolved else "skipped"
    bs.handoff_user_id = None
    out = meta_out(bs, task)
    await s.commit()
    return out
