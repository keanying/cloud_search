"""云端浏览器池：每个 worker 一个 Chromium 进程，每个任务运行一个独立 BrowserContext。

- context 之间 Cookie/存储隔离；单 context 内动作串行（asyncio.Lock）。
- 画面帧：每次导航/阶段变化后截取（限频），写入私有存储并更新 src_opr_browser_session_f，
  供右侧只读阅览读取。页面含密码输入框时不提供画面（masked）。
- 阅览只读取已有帧，绝不会因为“查看”而创建 context 或导航。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Route, async_playwright

from ..core.config import get_settings
from ..core.ids import new_id, utcnow
from ..core.storage import get_storage
from ..db.base import session_scope
from ..db.models import BrowserSession
from .guard import check_url, request_allowed

log = logging.getLogger(__name__)

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")


class CloudBrowserSession:
    def __init__(self, browser_session_id: str, context: BrowserContext, page: Page):
        self.browser_session_id = browser_session_id
        self.context = context
        self.page = page
        self.lock = asyncio.Lock()  # 单 context 串行动作
        self.challenge_reason: str | None = None  # 最近一次判定为验证/拦截的原因（排查用）
        self._frame_seq = 0
        self._last_frame = 0.0
        self._interval = get_settings().browser_frame_interval_s

    async def goto(self, url: str, *, activity: str | None = None, check: bool = True,
                   wait_until: str = "domcontentloaded"):
        if check:
            await check_url(url)
        await self.set_activity(activity)
        resp = await self.page.goto(url, wait_until=wait_until, timeout=get_settings().browser_nav_timeout_ms)
        await self.capture_frame(force=True)
        return resp

    async def settle(self, timeout_ms: int = 4000) -> None:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:  # noqa: BLE001  网络持续活跃的页面不阻塞
            pass

    async def set_activity(self, activity: str | None) -> None:
        if activity is None:
            return
        async with session_scope() as s:
            row = await s.get(BrowserSession, self.browser_session_id)
            if row:
                row.current_activity = activity[:128]

    async def capture_frame(self, *, force: bool = False) -> None:
        from .live import CHANNELS

        ch = CHANNELS.get(self.browser_session_id)
        if ch is not None and ch.handoff_active:
            return  # 人工接管期间画面只实时推送，不保存
        now = time.monotonic()
        if not force and now - self._last_frame < self._interval:
            return
        self._last_frame = now
        try:
            masked = await self.page.evaluate(
                "() => Array.from(document.querySelectorAll('input[type=password]')).some(e => e.offsetParent)")
            url, title = self.page.url, (await self.page.title())[:500]
            frame_ref = None
            if not masked:
                data = await self.page.screenshot(type="jpeg", quality=55, timeout=10000)
                frame_ref, _ = await get_storage().put(f"frames/{self.browser_session_id}/latest.jpg", data)
            self._frame_seq += 1
            async with session_scope() as s:
                row = await s.get(BrowserSession, self.browser_session_id)
                if row:
                    row.current_url, row.current_title = url[:2048], title
                    row.frame_masked = bool(masked)
                    if frame_ref:
                        row.frame_ref = frame_ref
                    row.frame_seq_no = self._frame_seq
                    row.frame_time = utcnow()
        except Exception as e:  # noqa: BLE001  截图失败不影响任务执行
            log.debug("capture_frame failed: %s", e)


class BrowserPool:
    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._start_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(get_settings().browser_max_contexts)

    async def _ensure(self) -> Browser:
        async with self._start_lock:
            if self._browser is None or not self._browser.is_connected():
                s = get_settings()
                self._pw = self._pw or await async_playwright().start()
                from .launch import resolve

                choice = resolve()
                if choice["mode"] == "error":
                    raise RuntimeError(choice["detail"])
                if choice["mode"] == "missing":
                    raise RuntimeError("未找到可用的浏览器：请运行启动脚本下载 Chromium，或在 config.yaml 设置 "
                                       "browser.channel: msedge / chrome（使用系统已安装的浏览器）")
                kwargs: dict = {"headless": s.browser_headless, **choice["launch_kwargs"]}
                if s.browser_slow_mo_ms > 0:
                    kwargs["slow_mo"] = s.browser_slow_mo_ms  # 调试：放慢每个动作，配合有头模式观察
                if s.browser_proxy:
                    kwargs["proxy"] = {"server": s.browser_proxy}
                self._browser = await self._pw.chromium.launch(**kwargs)
            return self._browser

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = self._pw = None

    @asynccontextmanager
    async def session(self, *, project_id: str, task_id: str, run_id: str, worker_id: str,
                      label: str) -> AsyncIterator[CloudBrowserSession]:
        async with self._sem:
            browser = await self._ensure()
            s = get_settings()
            context = await browser.new_context(
                locale=s.browser_locale, viewport={"width": 1280, "height": 860}, user_agent=DEFAULT_UA,
                accept_downloads=False, java_script_enabled=True, service_workers="block",
                permissions=[],
            )

            async def _guard(route: Route) -> None:
                if await request_allowed(route.request.url):
                    await route.continue_()
                else:
                    await route.abort("blockedbyclient")

            await context.route("**/*", _guard)
            page = await context.new_page()
            bsid = new_id("bs")
            from . import live

            async with session_scope() as db:
                db.add(BrowserSession(browser_session_id=bsid, project_id=project_id, task_id=task_id,
                                      run_id=run_id, worker_id=worker_id, session_label=label,
                                      session_status="active", live_endpoint=live.ADVERTISED_ENDPOINT))
            cs = CloudBrowserSession(bsid, context, page)
            live.register(bsid, cs)
            try:
                yield cs
            finally:
                try:
                    await live.unregister(bsid)
                    await context.close()
                finally:
                    async with session_scope() as db:
                        row = await db.get(BrowserSession, bsid)
                        if row:
                            row.session_status = "closed"
                            row.closed_time = utcnow()
                            row.current_activity = None


_pool: BrowserPool | None = None


def get_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        _pool = BrowserPool()
    return _pool
