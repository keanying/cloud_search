"""不开浏览器的 HTTP 搜索。

DuckDuckGo（主力）：直接使用 nickclyde/duckduckgo-mcp-server（PyPI: duckduckgo-mcp-server）的 DuckDuckGoSearcher：
  POST html.duckduckgo.com/html，Chrome 请求头，httpx 被拦（202/403/空页面）时自动改用 curl_cffi 模拟 Chrome TLS，
  内置滑动窗口限速与 429 Retry-After、去广告、解码跳转链接。
  在它之上补两点（子类）：走 config.yaml 的 browser.proxy（与云端浏览器同一出口）；支持时间范围（df=d/w/m/y）。
  仍然拿不到结果时由调用方退回浏览器搜索（遇到验证可请你接手）。
ddgs（补充）：deedy5/ddgs 多引擎聚合（Brave、Mojeek、Yahoo、Wikipedia 等），DuckDuckGo 被拦时作为不开浏览器的备选。
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from urllib.parse import parse_qs, unquote, urlsplit

from ..core.config import get_settings
from ..core.tracelog import trace

log = logging.getLogger(__name__)

RECENCY = {"day": "d", "week": "w", "month": "m", "year": "y"}
_df: contextvars.ContextVar[str | None] = contextvars.ContextVar("cs_ddg_df", default=None)


class HttpBlocked(Exception):
    """HTTP 方式没有拿到结果（被拦截、网络错误或页面变化），message 为原因。"""


def region(lang: str | None) -> str:
    return {"zh": "cn-zh", "en": "us-en"}.get(lang or "", "wt-wt")


def decode_link(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    p = urlsplit(href)
    if p.path.startswith("/l/") and "uddg" in p.query:
        return unquote(parse_qs(p.query)["uddg"][0])
    return href


class _TraceContext:
    """duckduckgo-mcp-server 需要的 MCP Context：把它的 info/error 写进执行日志，并记住错误。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    async def info(self, message: str, *args, **kwargs) -> None:
        self.notes.append(str(message))
        if "retrying with curl" in str(message) or "block" in str(message).lower():
            trace("search", f"duckduckgo-mcp-server：{message}")

    async def error(self, message: str, *args, **kwargs) -> None:
        self.errors.append(str(message))
        trace("search", f"duckduckgo-mcp-server 报错：{message}")

    async def debug(self, message: str, *args, **kwargs) -> None:
        pass

    async def warning(self, message: str, *args, **kwargs) -> None:
        self.notes.append(str(message))


_searcher = None
_searcher_key: tuple | None = None


def _make_searcher():
    """创建（并缓存）带代理与时间范围支持的 DuckDuckGoSearcher。"""
    global _searcher, _searcher_key
    import httpx
    from duckduckgo_mcp_server.server import DuckDuckGoSearcher, SafeSearchMode, _sleep_retry_after

    s = get_settings()
    key = (s.browser_proxy, s.search_ddg_rpm)
    if _searcher is not None and _searcher_key == key:
        return _searcher
    proxy = s.browser_proxy or None

    class CloudSearchDdg(DuckDuckGoSearcher):
        async def _request(self, data: dict, ctx) -> str:
            df = _df.get()
            return await super()._request({**data, "df": df} if df else data, ctx)

        async def _request_httpx(self, data: dict) -> tuple[int, str]:
            # 与上游实现相同，只是加上代理（上游没有代理参数）
            async with httpx.AsyncClient(verify=self.ssl_verify, proxy=proxy) as client:
                response = await client.post(self.BASE_URL, data=data, headers=self.HEADERS, timeout=30.0)
                if response.status_code == 429:
                    await _sleep_retry_after(response.headers)
                    response = await client.post(self.BASE_URL, data=data, headers=self.HEADERS, timeout=30.0)
                response.raise_for_status()
                return response.status_code, response.text

        async def _request_curl(self, data: dict) -> str:
            from curl_cffi.requests import AsyncSession

            async with AsyncSession(impersonate="chrome131", verify=self.ssl_verify, proxy=proxy) as client:
                response = await client.post(self.BASE_URL, data=data, timeout=30.0)
                if getattr(response, "status_code", None) == 429:
                    await _sleep_retry_after(getattr(response, "headers", None))
                    response = await client.post(self.BASE_URL, data=data, timeout=30.0)
                response.raise_for_status()
                return response.text

    _searcher = CloudSearchDdg(safe_search=SafeSearchMode.MODERATE, backend="auto",
                               requests_per_minute=s.search_ddg_rpm, ref_url_threshold=0)
    _searcher_key = key
    return _searcher


async def ddg_http_search(query: str, n: int, *, lang: str | None = None, recency: str | None = None) -> list[dict]:
    """用 duckduckgo-mcp-server 搜索 DuckDuckGo。返回 [{url, title, snippet}]；没有拿到结果时抛 HttpBlocked。"""
    searcher = _make_searcher()
    ctx = _TraceContext()
    token = _df.set(RECENCY.get(recency or ""))
    try:
        results = await searcher.search(query, ctx, max_results=max(n, 1), region=region(lang))
    finally:
        _df.reset(token)
    rows = [{"url": decode_link(r.link), "title": r.title, "snippet": r.snippet} for r in results
            if (r.link or "").startswith(("http://", "https://", "//"))]
    if rows:
        trace("search", f"duckduckgo（duckduckgo-mcp-server）：{len(rows)} 条")
        return rows
    why = "；".join(ctx.errors) or "没有返回结果（可能被拦截，或确实没有结果）"
    raise HttpBlocked(why[:300])


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
