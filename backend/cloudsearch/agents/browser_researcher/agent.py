"""浏览研究：默认程序化读页；正文不足时进入“观察→模型选一个动作→程序执行→重新观察”的串行循环。"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from ...browser.pool import CloudBrowserSession
from ...browser.reader import PageRead, extract_main_text, looks_blocked, read_url
from ..base import AgentRole, AgentSpec, ExecContext, run_agent
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import BrowserAction, ElementRef, Observation

SPEC: AgentSpec[BrowserAction] = AgentSpec(
    role=AgentRole.browser_researcher, output_type=BrowserAction, instructions=INSTRUCTIONS, request_limit=3)

MAX_INTERACTIVE_STEPS = 3
MIN_CHARS = 200

_OBSERVE_JS = r"""(token) => {
  document.querySelectorAll('[data-cs-ref]').forEach(e => e.removeAttribute('data-cs-ref'));
  const els = Array.from(document.querySelectorAll('a[href], button, [role=button], summary'));
  const out = []; let i = 0;
  for (const e of els) {
    if (!e.offsetParent) continue;
    const t = (e.innerText || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
    if (!t || t.length > 30) continue;
    if (/登录|注册|购买|支付|下载|login|sign in|register|buy|download/i.test(t)) continue;
    const id = token + '-' + (i++);
    e.setAttribute('data-cs-ref', id);
    out.push({element_id: id, kind: e.tagName.toLowerCase(), text: t});
    if (out.length >= 40) break;
  }
  return {url: location.href, title: document.title,
          text: (document.body ? document.body.innerText : '').slice(0, 1500), elements: out};
}"""


async def observe(s: CloudBrowserSession) -> Observation:
    token = secrets.token_hex(3)
    raw = await s.page.evaluate(_OBSERVE_JS, token)
    return Observation(observation_id=token, url=raw["url"], title=raw["title"], text_excerpt=raw["text"],
                       elements=[ElementRef(**e) for e in raw["elements"]])


async def _execute(s: CloudBrowserSession, obs: Observation, action: BrowserAction) -> bool:
    if action.action == "scroll":
        await s.page.mouse.wheel(0, 2500)
        await s.page.wait_for_timeout(1200)
        return True
    if action.action == "click":
        valid = {e.element_id for e in obs.elements}
        if action.element_id not in valid:  # 只接受当前观察签发的引用
            return False
        await s.page.locator(f'[data-cs-ref="{action.element_id}"]').first.click(timeout=8000)
        await s.settle(5000)
        return True
    return False


async def read_source(s: CloudBrowserSession, url: str, *, goal: str, ctx: ExecContext,
                      allow_interaction: bool = True,
                      on_blocked: Callable[[CloudBrowserSession, str], Awaitable[bool]] | None = None) -> PageRead:
    await ctx.check()
    result = await read_url(s, url, min_chars=MIN_CHARS)
    if result.status == "blocked" and on_blocked is not None and "HTTP" not in (result.reason or ""):
        # 验证码/登录墙：请用户在实时画面中处理，完成后直接读取当前页面
        if await on_blocked(s, f"网页需要验证或登录：{(result.title or url)[:60]}"):
            result = await read_url(s, url, min_chars=MIN_CHARS, navigate=False)
    if result.status != "no_content" or not allow_interaction:
        return result
    # 正文不足：有限步交互
    async with s.lock:
        for step in range(1, MAX_INTERACTIVE_STEPS + 1):
            await ctx.check()
            obs = await observe(s)
            if not obs.elements:
                break
            action = await run_agent(SPEC, build_prompt(goal, obs.model_dump_json(), step, MAX_INTERACTIVE_STEPS),
                                     ctx=ctx)
            if action.action == "finish":
                break
            try:
                if not await _execute(s, obs, action):
                    break
            except Exception:  # noqa: BLE001  动作失败：重新观察而不是盲目重放
                continue
            await s.capture_frame(force=True)
            html = await s.page.content()
            body = await s.page.evaluate("() => document.body ? document.body.innerText : ''")
            if looks_blocked(s.page.url, await s.page.title(), body):
                return PageRead("blocked", url, s.page.url, reason="交互后遇到验证/登录限制，未绕过")
            meta = extract_main_text(html, s.page.url)
            text = meta.get("text") or body
            if len(text) >= MIN_CHARS:
                result.status, result.text, result.final_url = "captured", text[:200_000], s.page.url
                result.title = meta.get("title") or result.title
                result.reason = None
                result.meta["interactive_steps"] = step
                break
    return result
