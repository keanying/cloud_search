"""实读：用云端浏览器真实打开页面并抽取正文。

- 导航成功、截图或搜索摘要都不等于实读；验证码页、登录壳、骨架屏不得作为正文。
- 发布时间/作者只取页面声明，未知为 None，不用读取时间代填。
- PDF 通过同一 context 的请求接口下载后解析（仍经出口检查）。
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import trafilatura
from pypdf import PdfReader

from .guard import UrlNotAllowed, check_url
from .pool import CloudBrowserSession

MAX_TEXT_CHARS = 200_000

BLOCK_URL_PATTERNS = re.compile(r"captcha|antispider|wappass|verify|/sorry/|challenge|login|signin|passport",
                                re.I)
BLOCK_TEXT_PATTERNS = re.compile(
    r"验证码|安全验证|人机验证|访问验证|异常流量|请完成验证|访问受限|Access Denied|captcha|are you a robot|"
    r"验证您是真人|验证你是真人|请解决以下难题|verify you are (a )?human|are you human|security check|"
    r"请先登录|登录后查看|403 Forbidden|Just a moment", re.I)


@dataclass
class PageRead:
    status: str  # captured / no_content / blocked / failed
    request_url: str
    final_url: str | None = None
    title: str | None = None
    text: str = ""
    site_name: str | None = None
    author: str | None = None
    publish_time_text: str | None = None
    reason: str | None = None
    meta: dict = field(default_factory=dict)


def blocked_reason(url: str, title: str, text: str) -> str | None:
    """页面是否像验证/登录/访问限制页；返回命中的规则（只对正文很短的页面判定）。"""
    if len(text) >= 800:
        return None
    m = BLOCK_URL_PATTERNS.search(urlsplit(url).path + "?" + (urlsplit(url).query or ""))
    if m:
        return f"正文很短（{len(text)} 字）且网址含“{m.group(0)}”"
    m = BLOCK_TEXT_PATTERNS.search(title + " " + text[:800])
    if m:
        return f"正文很短（{len(text)} 字）且含“{m.group(0)}”"
    return None


def looks_blocked(url: str, title: str, text: str) -> bool:
    return blocked_reason(url, title, text) is not None


async def _challenge_widget(s: CloudBrowserSession) -> str | None:
    from ..search.engines import CHALLENGE_JS

    try:
        return await s.page.evaluate(CHALLENGE_JS)
    except Exception:  # noqa: BLE001
        return None


def extract_main_text(html: str, url: str) -> dict:
    # 仅采用页面元数据中声明的日期（extensive_search=False），不做启发式猜测
    doc = trafilatura.bare_extraction(html, url=url, with_metadata=True, favor_recall=True,
                                      include_comments=False, include_tables=True,
                                      date_extraction_params={"extensive_search": False, "original_date": True})
    if doc is None:
        return {}
    d = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
    return {"text": d.get("text") or "", "title": d.get("title"), "author": d.get("author"),
            "date": d.get("date"), "sitename": d.get("sitename")}


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, p in enumerate(reader.pages[:60]):
        pages.append(f"[第{i + 1}页]\n{p.extract_text() or ''}")
    return "\n".join(pages)


async def _read_pdf(s: CloudBrowserSession, url: str) -> PageRead:
    resp = await s.context.request.get(url, timeout=60000, max_redirects=5)
    final_url = resp.url
    await check_url(final_url)
    if not resp.ok:
        return PageRead("failed", url, final_url, reason=f"HTTP {resp.status}")
    data = await resp.body()
    if len(data) > 30 * 1024 * 1024:
        return PageRead("failed", url, final_url, reason="PDF 超过 30MB 上限")
    text = _pdf_text(data)[:MAX_TEXT_CHARS]
    status = "captured" if len(text.strip()) > 200 else "no_content"
    return PageRead(status, url, final_url, title=urlsplit(final_url).path.rsplit("/", 1)[-1], text=text,
                    site_name=urlsplit(final_url).hostname, reason=None if status == "captured" else "PDF无可提取文本",
                    meta={"content_type": "application/pdf"})


async def read_url(s: CloudBrowserSession, url: str, *, min_chars: int = 200, activity: str | None = None,
                   navigate: bool = True) -> PageRead:
    """navigate=False：不重新打开，直接读取当前页面（人工接管处理完验证/登录后使用）。"""
    async with s.lock:
        try:
            await check_url(url)
        except UrlNotAllowed as e:
            return PageRead("failed", url, reason=str(e))
        try:
            if urlsplit(url).path.lower().endswith(".pdf"):
                await s.set_activity(activity or "读取 PDF")
                return await _read_pdf(s, url)
            resp = None
            if navigate:
                try:
                    resp = await s.goto(url, activity=activity or "读取网页", check=False)
                except Exception as e:  # noqa: BLE001
                    if "Download is starting" in str(e):
                        return await _read_pdf(s, url)
                    raise
            ctype = (resp.headers.get("content-type", "") if resp else "").lower()
            if "pdf" in ctype:
                return await _read_pdf(s, s.page.url)
            await s.settle()
            final_url = s.page.url
            await check_url(final_url)  # 重定向终点再检查
            title = await s.page.title()
            html = await s.page.content()
            body_text = await s.page.evaluate("() => document.body ? document.body.innerText : ''")
            await s.capture_frame(force=True)
            if resp is not None and resp.status >= 400:
                status = "blocked" if resp.status in (401, 403, 429) else "failed"
                return PageRead(status, url, final_url, title=title, reason=f"HTTP {resp.status}")
            why = blocked_reason(final_url, title, body_text)
            if why is None and len(body_text) < 1500:
                widget = await _challenge_widget(s)
                why = f"正文较短（{len(body_text)} 字）且有可见的验证组件：{widget}" if widget else None
            if why:
                from ..search.engines import record_challenge

                await record_challenge(s, why, "读取网页")
                return PageRead("blocked", url, final_url, title=title, reason=f"遇到验证/登录/访问限制，未绕过（{why}）"[:250])
            meta = extract_main_text(html, final_url)
            text = meta.get("text") or ""
            if len(text) < min_chars and len(body_text) > len(text):
                text = body_text  # 正文抽取失败时退回可见文本
            text = re.sub(r"\n{3,}", "\n\n", text).strip()[:MAX_TEXT_CHARS]
            status = "captured" if len(text) >= min_chars else "no_content"
            return PageRead(status, url, final_url, title=meta.get("title") or title, text=text,
                            site_name=meta.get("sitename") or urlsplit(final_url).hostname,
                            author=meta.get("author"), publish_time_text=meta.get("date"),
                            reason=None if status == "captured" else "页面正文过短",
                            meta={"content_type": ctype})
        except UrlNotAllowed as e:
            return PageRead("failed", url, reason=str(e))
        except Exception as e:  # noqa: BLE001
            return PageRead("failed", url, final_url=s.page.url if s.page else None,
                            reason=f"{type(e).__name__}: {str(e)[:200]}")
