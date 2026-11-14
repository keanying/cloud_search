"""实时通道的 WebSocket 服务逻辑（API 直连与 worker 内部通道共用）。

消息协议（JSON）：
  服务端→前端：{"type":"frame",...} / {"type":"status",...} / {"type":"error","message":...}
  前端→服务端（仅 interactive=true 时处理）：{"type":"mouse"|"key"|"text",...}
interactive 由数据库中的接管状态决定：handoff_state=active 且 handoff_user_id 为当前用户。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import logging
import socket

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from ..core.config import get_settings
from ..core.ids import iso
from ..db.base import session_scope
from ..db.models import BrowserSession
from . import live

log = logging.getLogger(__name__)

INPUT_TYPES = {"mouse", "key", "text", "reload"}


def internal_signature(browser_session_id: str, user_id: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"live:{browser_session_id}:{user_id}".encode(), hashlib.sha256).hexdigest()


async def _status(browser_session_id: str, user_id: str) -> dict:
    async with session_scope() as db:
        row = await db.get(BrowserSession, browser_session_id)
        if row is None:
            return {"type": "status", "session_status": "closed", "handoff_state": "none", "handoff_reason": None,
                    "handoff_deadline": None, "interactive": False}
        return {"type": "status", "session_status": row.session_status, "handoff_state": row.handoff_state,
                "handoff_reason": row.handoff_reason, "handoff_deadline": iso(row.handoff_deadline),
                "interactive": row.handoff_state == "active" and row.handoff_user_id == user_id}


async def serve_channel(ws: WebSocket, browser_session_id: str, user_id: str) -> None:
    """在本进程内为一个已 accept 的 WebSocket 提供实时画面与（接管时的）输入转发。"""
    ch = live.CHANNELS.get(browser_session_id)
    if ch is None:
        await ws.send_json({"type": "error", "message": "云端浏览器会话不在线"})
        await ws.close()
        return
    q = await ch.subscribe()
    state = {"interactive": False}

    async def sender():
        while True:
            await ws.send_json(await q.get())

    async def status_loop():
        last = None
        while True:
            st = await _status(browser_session_id, user_id)
            state["interactive"] = st["interactive"]
            if st != last:
                await ws.send_json(st)
                last = st
            if st["session_status"] != "active":
                return
            await asyncio.sleep(1.0)

    async def receiver():
        while True:
            ev = await ws.receive_json()
            if ev.get("type") in INPUT_TYPES and state["interactive"]:
                try:
                    await ch.dispatch(ev)
                except Exception as e:  # noqa: BLE001  单次输入失败不中断通道
                    log.debug("dispatch failed: %s", e)

    tasks = [asyncio.create_task(c()) for c in (sender, status_loop, receiver)]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await ch.unsubscribe(q)
        with contextlib.suppress(Exception):
            await ws.close()


# ---------------------------------------------------------------- worker 内部通道（多进程部署时由 API 转发）
def build_internal_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.websocket("/internal/live/{browser_session_id}")
    async def internal_live(ws: WebSocket, browser_session_id: str, uid: str, sig: str):
        if not hmac.compare_digest(sig, internal_signature(browser_session_id, uid)):
            await ws.close(code=4403)
            return
        await ws.accept()
        await serve_channel(ws, browser_session_id, uid)

    return app


async def start_internal_server() -> asyncio.Task:
    """独立 worker 启动内部实时通道（随机端口），并公布地址供 API 转发。"""
    import uvicorn

    s = get_settings()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((s.worker_live_bind, 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(build_internal_app(), log_level="warning", lifespan="off"))
    server.capture_signals = contextlib.nullcontext  # 不接管信号，由 worker 自己处理
    task = asyncio.create_task(server.serve(sockets=[sock]))
    live.ADVERTISED_ENDPOINT = f"ws://{s.worker_live_advertise_host}:{port}"
    log.info("worker live channel at %s", live.ADVERTISED_ENDPOINT)
    return task
