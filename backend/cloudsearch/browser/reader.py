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


def looks_blocked(url: str, title: str, text: str) -> bool:
    short = len(text) < 800
    return bool(BLOCK_URL_PATTERNS.search(urlsplit(url).path + "?" + (urlsplit(url).query or ""))
                and short) or bool(short and BLOCK_TEXT_PATTERNS.search(title + " " + text[:800]))


def extract_main_text(html: str, url: str) -> dict:
    doc = trafilatura.bare_extraction(html, url=url, with_metadata=True, favor_recall=True,
                                      include_comments=False, include_tables=True)
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


async def read_url(s: CloudBrowserSession, url: str, *, min_chars: int = 200, activity: str | None = None) -> PageRead:
    async with s.lock:
        try:
            await check_url(url)
        except UrlNotAllowed as e:
            return PageRead("failed", url, reason=str(e))
        try:
            if urlsplit(url).path.lower().endswith(".pdf"):
                await s.set_activity(activity or "读取 PDF")
                return await _read_pdf(s, url)
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
            if looks_blocked(final_url, title, body_text):
                return PageRead("blocked", url, final_url, title=title, reason="遇到验证/登录/访问限制，未绕过")
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
