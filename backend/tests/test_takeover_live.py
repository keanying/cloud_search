"""实时画面 + 人工接管端到端：真实浏览器、真实 CDP 推流与输入转发、真实 WebSocket。"""

from __future__ import annotations

import asyncio
import json
import socket

import httpx
import pytest
import uvicorn

CAPTCHA_PAGE = """<html><body style="font:16px sans-serif">
<h1 id="h">请完成人机验证</h1>
<button id="b" style="position:absolute;left:100px;top:200px;width:200px;height:60px"
  onclick="document.getElementById('h').textContent='验证通过'">我不是机器人</button>
<input id="i" style="position:absolute;left:100px;top:300px;width:200px" />
</body></html>"""


class StubCtx:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.step_id = None

    async def check(self):
        return None


@pytest.fixture
async def live_server(env, monkeypatch):
    from cloudsearch.app import create_app

    for k in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(k, "127.0.0.1,localhost")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning",
                                           lifespan="off"))
    server.capture_signals = __import__("contextlib").nullcontext
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task


async def test_live_view_and_takeover_with_real_browser(live_server):
    import websockets

    from cloudsearch.browser.launch import resolve
    from cloudsearch.browser.pool import BrowserPool
    from cloudsearch.db.base import session_scope
    from cloudsearch.db.models import Task
    from cloudsearch.orchestrator.takeover import request_takeover

    if resolve()["mode"] in ("missing", "error"):
        pytest.skip("无可用浏览器")
    async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
        owner = (await c.post("/api/v1/auth/register", json={"username": "owner", "password": "secret123"})).json()
        other = (await c.post("/api/v1/auth/register", json={"username": "other", "password": "secret123"})).json()
        h = {"Authorization": f"Bearer {owner['access_token']}"}
        h2 = {"Authorization": f"Bearer {other['access_token']}"}
        async with session_scope() as db:
            db.add(Task(task_id="task_live", project_id=owner["user"]["project_id"], created_by_id=owner["user"]["user_id"],
                        mode="quick_search", title="t", task_spec={}, task_status="running"))
        pool = BrowserPool()
        try:
            async with pool.session(project_id=owner["user"]["project_id"], task_id="task_live", run_id="r",
                                    worker_id="w", label="会话1") as sess:
                await sess.page.set_content(CAPTCHA_PAGE)
                bsid = sess.browser_session_id
                waiter = asyncio.create_task(request_takeover(StubCtx("task_live"), bsid, "搜索引擎要求人机验证"))
                for _ in range(50):
                    meta = (await c.get(f"/api/v1/browser-sessions/{bsid}/viewer-meta", headers=h)).json()
                    if meta["handoff_state"] == "requested":
                        break
                    await asyncio.sleep(0.1)
                assert meta["handoff_state"] == "requested" and meta["live_available"] is True
                assert "人机验证" in meta["handoff_reason"]

                # 实时画面：票据 + WebSocket，先收到真实帧，接管前不可交互
                t = (await c.post(f"/api/v1/browser-sessions/{bsid}/live-ticket", headers=h)).json()
                assert t["interactive"] is False
                ws_url = live_server.replace("http", "ws") + f"/api/v1/browser-sessions/{bsid}/live?ticket={t['ticket']}"
                async with websockets.connect(ws_url, max_size=None) as ws:
                    got_frame = got_status = False
                    for _ in range(40):
                        m = json.loads(await asyncio.wait_for(ws.recv(), 10))
                        got_frame |= m["type"] == "frame" and len(m["data"]) > 1000
                        if m["type"] == "status":
                            got_status = True
                            assert m["interactive"] is False and m["handoff_state"] == "requested"
                        if got_frame and got_status:
                            break
                    assert got_frame and got_status
                    # 接管前发送的点击被忽略
                    await ws.send(json.dumps({"type": "mouse", "action": "down", "x": 200, "y": 230, "button": "left",
                                              "clickCount": 1}))
                    await ws.send(json.dumps({"type": "mouse", "action": "up", "x": 200, "y": 230, "button": "left",
                                              "clickCount": 1}))
                    await asyncio.sleep(0.5)
                    assert await sess.page.inner_text("#h") == "请完成人机验证"

                    # 他人不能接管；本人接管后输入生效
                    assert (await c.post(f"/api/v1/browser-sessions/{bsid}/takeover", headers=h2)).status_code == 404
                    r = await c.post(f"/api/v1/browser-sessions/{bsid}/takeover", headers=h)
                    assert r.status_code == 200 and r.json()["handoff_state"] == "active"
                    for _ in range(40):
                        m = json.loads(await asyncio.wait_for(ws.recv(), 10))
                        if m["type"] == "status" and m["interactive"]:
                            break
                    else:
                        raise AssertionError("未收到可交互状态")
                    for action in ("move", "down", "up"):
                        await ws.send(json.dumps({"type": "mouse", "action": action, "x": 200, "y": 230,
                                                  "button": "left", "clickCount": 1}))
                    await ws.send(json.dumps({"type": "mouse", "action": "down", "x": 150, "y": 310, "button": "left",
                                              "clickCount": 1}))
                    await ws.send(json.dumps({"type": "mouse", "action": "up", "x": 150, "y": 310, "button": "left",
                                              "clickCount": 1}))
                    await ws.send(json.dumps({"type": "text", "text": "验证码ab"}))
                    await ws.send(json.dumps({"type": "key", "action": "down", "key": "Backspace", "code": "Backspace"}))
                    await ws.send(json.dumps({"type": "key", "action": "up", "key": "Backspace", "code": "Backspace"}))
                    for _ in range(30):
                        if await sess.page.inner_text("#h") == "验证通过":
                            break
                        await asyncio.sleep(0.1)
                    assert await sess.page.inner_text("#h") == "验证通过"  # CDP 点击已转发
                    assert await sess.page.input_value("#i") == "验证码a"  # 文本输入与退格键已转发

                # 交还给 AI → 等待结束并返回 True
                r = await c.post(f"/api/v1/browser-sessions/{bsid}/takeover/return", headers=h, json={"resolved": True})
                assert r.status_code == 200
                assert await asyncio.wait_for(waiter, 10) is True
                meta = (await c.get(f"/api/v1/browser-sessions/{bsid}/viewer-meta", headers=h)).json()
                assert meta["handoff_state"] == "resolved"
                # 票据错误被拒绝
                with pytest.raises(Exception):
                    async with websockets.connect(live_server.replace("http", "ws") +
                                                  f"/api/v1/browser-sessions/{bsid}/live?ticket=bad") as ws:
                        await asyncio.wait_for(ws.recv(), 5)
        finally:
            await pool.close()


async def test_takeover_times_out_without_human(env, monkeypatch):
    from cloudsearch.core import config
    from cloudsearch.core.ids import new_id
    from cloudsearch.db.base import session_scope
    from cloudsearch.db.models import BrowserSession
    from cloudsearch.orchestrator.takeover import request_takeover

    monkeypatch.setenv("CS_BROWSER_TAKEOVER_TIMEOUT_S", "1")
    config.get_settings.cache_clear()
    bsid = new_id("bs")
    async with session_scope() as db:
        db.add(BrowserSession(browser_session_id=bsid, project_id="p", task_id="t", run_id="r", worker_id="w",
                              session_label="s", session_status="active"))
    assert await request_takeover(StubCtx("t"), bsid, "验证") is False
    async with session_scope() as db:
        assert (await db.get(BrowserSession, bsid)).handoff_state == "timeout"
    config.get_settings.cache_clear()


async def test_live_relay_through_worker_internal_channel(live_server, monkeypatch):
    """多进程部署：API 进程看不到浏览器对象，通过 worker 内部通道转发画面与输入。"""
    import types

    import websockets

    from cloudsearch.api.routers import viewer
    from cloudsearch.browser import live
    from cloudsearch.browser.launch import resolve
    from cloudsearch.browser.live_server import start_internal_server
    from cloudsearch.browser.pool import BrowserPool
    from cloudsearch.db.base import session_scope
    from cloudsearch.db.models import Task

    if resolve()["mode"] in ("missing", "error"):
        pytest.skip("无可用浏览器")
    internal = await start_internal_server()  # worker 侧内部通道
    try:
        async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
            owner = (await c.post("/api/v1/auth/register", json={"username": "owner2", "password": "secret123"})).json()
            h = {"Authorization": f"Bearer {owner['access_token']}"}
            async with session_scope() as db:
                db.add(Task(task_id="task_relay", project_id=owner["user"]["project_id"],
                            created_by_id=owner["user"]["user_id"], mode="quick_search", title="t", task_spec={},
                            task_status="running"))
            pool = BrowserPool()
            try:
                async with pool.session(project_id=owner["user"]["project_id"], task_id="task_relay", run_id="r",
                                        worker_id="w", label="会话1") as sess:
                    await sess.page.set_content(CAPTCHA_PAGE)
                    bsid = sess.browser_session_id
                    # 让 API 侧“看不到”本进程的浏览器，强制走转发
                    monkeypatch.setattr(viewer, "live", types.SimpleNamespace(CHANNELS={}))
                    meta = (await c.get(f"/api/v1/browser-sessions/{bsid}/viewer-meta", headers=h)).json()
                    assert meta["live_available"] is True
                    t = (await c.post(f"/api/v1/browser-sessions/{bsid}/live-ticket", headers=h)).json()
                    async with session_scope() as db:  # 模拟系统已请求并由本人接管
                        from cloudsearch.db.models import BrowserSession

                        row = await db.get(BrowserSession, bsid)
                        row.handoff_state, row.handoff_user_id = "active", owner["user"]["user_id"]
                    url = live_server.replace("http", "ws") + f"/api/v1/browser-sessions/{bsid}/live?ticket={t['ticket']}"
                    async with websockets.connect(url, max_size=None) as ws:
                        frame = interactive = False
                        for _ in range(40):
                            m = json.loads(await asyncio.wait_for(ws.recv(), 10))
                            frame |= m["type"] == "frame"
                            interactive |= m["type"] == "status" and m["interactive"]
                            if frame and interactive:
                                break
                        assert frame and interactive
                        for action in ("down", "up"):
                            await ws.send(json.dumps({"type": "mouse", "action": action, "x": 200, "y": 230,
                                                      "button": "left", "clickCount": 1}))
                        for _ in range(30):
                            if await sess.page.inner_text("#h") == "验证通过":
                                break
                            await asyncio.sleep(0.1)
                        assert await sess.page.inner_text("#h") == "验证通过"
            finally:
                await pool.close()
    finally:
        internal.cancel()
        live.ADVERTISED_ENDPOINT = None
