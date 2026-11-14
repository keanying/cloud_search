"""实时阅览与人工接管（CDP）。

- 画面：Page.startScreencast 推送 JPEG 帧（有人观看时才开启，最后一个观看者离开即停止），经 WebSocket 发给前端。
- 输入：人工接管期间，把前端的鼠标/键盘/文本事件通过 Input.dispatch* 转发到云端页面。
- 只在本进程内持有真实浏览器对象；多进程部署时由 worker 的内部通道（见 live_server.py）提供给 API 转发。
- 接管期间的帧只实时推送，不落盘；AI 在接管期间不对该页面执行任何动作（调用方在等待接管结果）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

log = logging.getLogger(__name__)

# 常用功能键的 Windows 虚拟键码（CDP 需要它们才能触发回车、退格等默认行为）
_VK = {"Enter": 13, "Backspace": 8, "Tab": 9, "Escape": 27, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39,
       "ArrowDown": 40, "Delete": 46, "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34, " ": 32}
_MOUSE = {"move": "mouseMoved", "down": "mousePressed", "up": "mouseReleased", "wheel": "mouseWheel"}


class LiveChannel:
    """一个云端浏览器会话的实时通道。"""

    def __init__(self, browser_session_id: str, session: Any):
        self.browser_session_id = browser_session_id
        self.session = session  # CloudBrowserSession
        self.subscribers: set[asyncio.Queue] = set()
        self._cdp = None
        self._casting = False
        self._seq = 0
        self._lock = asyncio.Lock()
        self.handoff_active = False  # 接管期间：不保存截图帧

    async def _ensure_cdp(self):
        if self._cdp is None:
            self._cdp = await self.session.context.new_cdp_session(self.session.page)
            self._cdp.on("Page.screencastFrame", self._on_frame)
        return self._cdp

    def _on_frame(self, params: dict) -> None:
        self._seq += 1
        meta = params.get("metadata", {})
        msg = {"type": "frame", "data": params["data"], "width": int(meta.get("deviceWidth") or 1280),
               "height": int(meta.get("deviceHeight") or 860), "seq": self._seq,
               "url": self.session.page.url, "title": ""}
        for q in list(self.subscribers):
            if q.qsize() > 3:  # 观看端太慢：丢弃旧帧，保持实时
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(msg)
        if self._cdp is not None:
            asyncio.ensure_future(self._ack(params["sessionId"]))

    async def _ack(self, sid: int) -> None:
        with contextlib.suppress(Exception):
            await self._cdp.send("Page.screencastFrameAck", {"sessionId": sid})

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self.subscribers.add(q)
            if not self._casting:
                cdp = await self._ensure_cdp()
                await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 60, "maxWidth": 1280,
                                                        "maxHeight": 860, "everyNthFrame": 1})
                self._casting = True
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self.subscribers.discard(q)
            if not self.subscribers and self._casting and self._cdp is not None:
                with contextlib.suppress(Exception):
                    await self._cdp.send("Page.stopScreencast")
                self._casting = False

    async def dispatch(self, ev: dict) -> None:
        """转发人工输入（调用方负责校验接管权限）。"""
        cdp = await self._ensure_cdp()
        t = ev.get("type")
        if t == "mouse":
            kind = _MOUSE.get(ev.get("action", ""))
            if not kind:
                return
            p = {"type": kind, "x": float(ev.get("x", 0)), "y": float(ev.get("y", 0)),
                 "button": ev.get("button", "left") if kind != "mouseMoved" else "none",
                 "clickCount": int(ev.get("clickCount", 1)) if kind in ("mousePressed", "mouseReleased") else 0}
            if kind == "mouseWheel":
                p.update(deltaX=float(ev.get("deltaX", 0)), deltaY=float(ev.get("deltaY", 0)))
            await cdp.send("Input.dispatchMouseEvent", p)
        elif t == "key":
            key = str(ev.get("key", ""))
            text = ev.get("text")
            p = {"type": "keyDown" if ev.get("action") == "down" else "keyUp", "key": key,
                 "code": str(ev.get("code", ""))}
            if key in _VK:
                p["windowsVirtualKeyCode"] = p["nativeVirtualKeyCode"] = _VK[key]
            if p["type"] == "keyDown" and text and len(text) == 1:
                p["text"] = text
            await cdp.send("Input.dispatchKeyEvent", p)
        elif t == "text" and ev.get("text"):
            await cdp.send("Input.insertText", {"text": str(ev["text"])[:2000]})
        elif t == "reload":  # 验证组件没加载出来时，由接手的用户刷新页面
            await cdp.send("Page.reload", {"ignoreCache": True})

    async def close(self) -> None:
        for q in list(self.subscribers):
            q.put_nowait({"type": "status", "session_status": "closed", "handoff_state": "none",
                          "handoff_reason": None, "handoff_deadline": None, "interactive": False})
        self.subscribers.clear()
        if self._cdp is not None:
            with contextlib.suppress(Exception):
                await self._cdp.detach()
        self._cdp = None


# 本进程内的通道注册表
CHANNELS: dict[str, LiveChannel] = {}
# 本进程内部实时通道的对外地址（独立 worker 进程启动内部通道后设置；嵌入模式为 None，API 直接访问 CHANNELS）
ADVERTISED_ENDPOINT: str | None = None


def register(browser_session_id: str, session: Any) -> LiveChannel:
    ch = LiveChannel(browser_session_id, session)
    CHANNELS[browser_session_id] = ch
    return ch


async def unregister(browser_session_id: str) -> None:
    ch = CHANNELS.pop(browser_session_id, None)
    if ch is not None:
        await ch.close()
