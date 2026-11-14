"""不开浏览器的 HTTP 搜索（参考 nickclyde/duckduckgo-mcp-server 与 deedy5/ddgs）。

DuckDuckGo（主力）：POST https://html.duckduckgo.com/html，表单 q / b / kl（地区）/ kp（安全搜索）/ df（时间范围），
  带 Chrome 请求头；解析 .result / .result__title a / .result__snippet，去广告（y.js）、解码 uddg 跳转。
  被拦（HTTP 202/403、空页面、异常流量页）时改用 curl_cffi 模拟 Chrome 的 TLS 指纹重试；仍不行再由调用方退回浏览器搜索。
  滑动窗口限速（默认每分钟 30 次），429 时按 Retry-After（最多 30 秒）重试一次。
ddgs（补充）：多引擎聚合（Brave、Mojeek、Yahoo、Wikipedia 等），DuckDuckGo 被拦时作为不开浏览器的备选。
两者都走 config.yaml 的 browser.proxy（与云端浏览器同一出口）。
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from urllib.parse import parse_qs, unquote, urlsplit

from ..core.config import get_settings
from ..core.tracelog import trace

log = logging.getLogger(__name__)

DDG_HTML = "https://html.duckduckgo.com/html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/139.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://html.duckduckgo.com",
    "Referer": "https://html.duckduckgo.com/",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1", "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    "Sec-Ch-Ua-Mobile": "?0", "Sec-Ch-Ua-Platform": '"Windows"',
}
RECENCY = {"day": "d", "week": "w", "month": "m", "year": "y"}


class HttpBlocked(Exception):
    """HTTP 方式被拦截（202/403/空页面/异常流量页），message 为原因。"""


def region(lang: str | None) -> str:
    return {"zh": "cn-zh", "en": "us-en"}.get(lang or "", "wt-wt")


class SlidingWindow:
    """进程内滑动窗口限速：60 秒内最多 rpm 次。"""

    def __init__(self) -> None:
        self.calls: collections.deque[float] = collections.deque()
        self.lock = asyncio.Lock()

    async def acquire(self, rpm: int) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.calls and now - self.calls[0] > 60:
                    self.calls.popleft()
                if len(self.calls) < max(1, rpm):
                    self.calls.append(now)
                    return
                await asyncio.sleep(60 - (now - self.calls[0]) + 0.05)


_ddg_limiter = SlidingWindow()


def decode_link(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    p = urlsplit(href)
    if p.path.startswith("/l/") and "uddg" in p.query:
        return unquote(parse_qs(p.query)["uddg"][0])
    return href


def parse_ddg_html(html: str) -> list[dict]:
    """解析 DuckDuckGo HTML 版结果页 → [{url, title, snippet}]（去广告、解码跳转）。"""
    from lxml import html as lh

    def has(cls: str) -> str:  # XPath：class 属性里包含某个类名（不依赖 cssselect）
        return f"contains(concat(' ', normalize-space(@class), ' '), ' {cls} ')"

    doc = lh.fromstring(html)
    out = []
    for r in doc.xpath(f"//*[{has('result')}]"):
        cls = r.get("class") or ""
        if "result--ad" in cls:
            continue
        a = r.xpath(f".//*[{has('result__title')}]//a") or r.xpath(f".//a[{has('result__a')}]")
        if not a:
            continue
        href = decode_link(a[0].get("href") or "")
        if not href.startswith(("http://", "https://")) or "duckduckgo.com/y.js" in href:
            continue
        sn = r.xpath(f".//*[{has('result__snippet')}]")
        out.append({"url": href, "title": a[0].text_content().strip(),
                    "snippet": sn[0].text_content().strip() if sn else None})
    return out


def _block_reason(status: int, text: str) -> str | None:
    if status in (202, 403):
        return f"HTTP {status}（DuckDuckGo 判定为异常流量）"
    if status == 200 and not text.strip():
        return "返回了空页面"
    low = text[:4000].lower()
    if "anomaly-modal" in low or "unusual traffic" in low or "bots use duckduckgo" in low:
        return "返回了异常流量验证页"
    return None


async def _post_httpx(data: dict) -> tuple[int, str, dict]:
    import httpx

    proxy = get_settings().browser_proxy or None
    async with httpx.AsyncClient(timeout=20, proxy=proxy, follow_redirects=True) as c:
        r = await c.post(DDG_HTML, data=data, headers=HEADERS)
        return r.status_code, r.text, dict(r.headers)


async def _post_curl(data: dict) -> tuple[int, str, dict]:
    from curl_cffi.requests import AsyncSession

    proxy = get_settings().browser_proxy or None
    async with AsyncSession(impersonate="chrome131") as c:
        r = await c.post(DDG_HTML, data=data, timeout=20, proxy=proxy)
        return r.status_code, r.text, dict(r.headers)


async def ddg_http_search(query: str, n: int, *, lang: str | None = None, recency: str | None = None) -> list[dict]:
    """DuckDuckGo HTML 接口搜索。返回原始结果行；被拦截时抛 HttpBlocked。"""
    s = get_settings()
    data = {"q": query, "b": "", "kl": region(lang), "kp": "-1"}
    if recency in RECENCY:
        data["df"] = RECENCY[recency]
    reasons = []
    for name, post in (("httpx", _post_httpx), ("curl_cffi", _post_curl)):
        await _ddg_limiter.acquire(s.search_ddg_rpm)
        t0 = time.monotonic()
        try:
            status, text, headers = await post(data)
            if status == 429:  # 限流：按 Retry-After 等待后重试一次
                wait = min(30.0, float(headers.get("retry-after") or headers.get("Retry-After") or 5))
                trace("search", f"duckduckgo（HTTP/{name}）被限流，{wait:.0f}s 后重试")
                await asyncio.sleep(wait)
                status, text, headers = await post(data)
        except Exception as e:  # noqa: BLE001 —— 网络不通、TLS 错误、未安装 curl_cffi 等
            reasons.append(f"{name}: {type(e).__name__} {str(e)[:120]}")
            continue
        why = _block_reason(status, text)
        if why:
            reasons.append(f"{name}: {why}")
            trace("search", f"duckduckgo（HTTP/{name}）被拦截：{why}（{time.monotonic() - t0:.1f}s）")
            continue
        if status != 200:
            reasons.append(f"{name}: HTTP {status}")
            continue
        rows = parse_ddg_html(text)
        if not rows and "no-results" not in text and "No results" not in text and "没有结果" not in text:
            reasons.append(f"{name}: 页面里没有解析到结果（页面结构可能变化）")
            continue
        trace("search", f"duckduckgo（HTTP/{name}）：{len(rows)} 条（{time.monotonic() - t0:.1f}s）")
        return rows[: max(n, 1)]
    raise HttpBlocked("；".join(reasons) or "未知原因")


async def ddgs_search(query: str, n: int, *, lang: str | None = None, recency: str | None = None) -> list[dict]:
    """ddgs 多引擎聚合搜索（同步库，放到线程里跑）。返回 [{url, title, snippet, source}]。"""
    s = get_settings()

    def run() -> list[dict]:
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

        try:
            rows = DDGS(proxy=s.browser_proxy or None, timeout=15).text(
                query, region=region(lang), safesearch="moderate", timelimit=RECENCY.get(recency or ""),
                max_results=n, backend=s.search_ddgs_backends)
        except (RatelimitException, TimeoutException):
            raise
        except DDGSException as e:
            if "no results" in str(e).lower():
                return []
            raise
        return [{"url": r.get("href"), "title": r.get("title"), "snippet": r.get("body")} for r in rows
                if r.get("href", "").startswith(("http://", "https://"))]

    return await asyncio.to_thread(run)
