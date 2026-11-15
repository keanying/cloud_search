"""先用 HTTP 读取网页（不开浏览器）：curl_cffi 模拟 Chrome 的 TLS 指纹 + trafilatura 抽取正文。

打开真实浏览器访问网站更容易触发人机验证，而大部分文章页用普通请求就能拿到正文。
browser.read_mode=auto 时先走这里，拿不到正文（需要执行脚本的页面、被拦截、正文太短）再交给云端浏览器。
出口防护：每一跳重定向都经过 check_url（禁止内网/保留地址）。代理与浏览器一致（browser.proxy / proxy_bypass）。
"""

from __future__ import annotations

import fnmatch
import time
from urllib.parse import urljoin, urlsplit

from ..core.config import get_settings
from .guard import check_url
from .reader import MAX_TEXT_CHARS, PageRead, _pdf_text, blocked_reason, extract_images, extract_main_text, pdf_title

MAX_HTML_BYTES = 6 * 1024 * 1024
MAX_PDF_BYTES = 30 * 1024 * 1024
CHALLENGE_MARKERS = ("cf-mitigated", "challenges.cloudflare.com", "Just a moment...", "Enable JavaScript and cookies",
                     "Checking your browser", "g-recaptcha", "h-captcha", "geetest", "安全验证", "人机验证")


def _proxy_for(url: str) -> str | None:
    s = get_settings()
    if not s.browser_proxy:
        return None
    host = (urlsplit(url).hostname or "").lower()
    for pat in s.browser_proxy_bypass:
        p = pat.strip().lower()
        if not p:
            continue
        if p.startswith("."):
            p = "*" + p
        if fnmatch.fnmatch(host, p) or host == p.lstrip("*."):
            return None
    return s.browser_proxy


def _title_and_text(html: str) -> tuple[str, str]:
    """(页面标题, 去掉脚本样式后的可见文字)"""
    from lxml import html as lh

    try:
        doc = lh.fromstring(html)
    except (ValueError, TypeError, lh.etree.ParserError):
        return "", ""
    title = (doc.findtext(".//title") or "").strip()
    for bad in doc.xpath("//script|//style|//noscript"):
        bad.drop_tree()
    return title, " ".join(doc.text_content().split())


async def read_http(url: str, *, min_chars: int = 200) -> PageRead:
    """返回 PageRead（status：captured / no_content / blocked / failed）。不抛异常。"""
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return PageRead("failed", url, reason="未安装 curl_cffi")
    t0 = time.monotonic()
    cur = url
    try:
        async with AsyncSession(impersonate="chrome131") as client:
            resp = None
            for _ in range(6):  # 手动跟随重定向：每一跳都做出口检查
                await check_url(cur)
                resp = await client.get(cur, allow_redirects=False, timeout=20, proxy=_proxy_for(cur),
                                        headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
                loc = resp.headers.get("location")
                if resp.status_code in (301, 302, 303, 307, 308) and loc:
                    cur = urljoin(cur, loc)
                    continue
                break
    except Exception as e:  # noqa: BLE001 —— 网络错误、出口防护拒绝等
        return PageRead("failed", url, cur, reason=f"HTTP 读取失败：{type(e).__name__} {str(e)[:120]}")
    final = cur
    status = resp.status_code
    if status in (401, 403, 429):
        return PageRead("blocked", url, final, reason=f"HTTP {status}")
    if status >= 400:
        return PageRead("failed", url, final, reason=f"HTTP {status}")
    ctype = (resp.headers.get("content-type") or "").lower()
    body = resp.content or b""
    if "pdf" in ctype or final.lower().endswith(".pdf"):
        if len(body) > MAX_PDF_BYTES:
            return PageRead("failed", url, final, reason="PDF 超过 30MB 上限")
        text = _pdf_text(body)[:MAX_TEXT_CHARS]
        st = "captured" if len(text.strip()) > min_chars else "no_content"
        return PageRead(st, url, final, title=pdf_title(body, text, final), text=text,
                        site_name=urlsplit(final).hostname, reason=None if st == "captured" else "PDF无可提取文本",
                        meta={"via": "http", "ms": int((time.monotonic() - t0) * 1000)})
    if ctype and not any(t in ctype for t in ("html", "xml", "text/plain")):
        return PageRead("failed", url, final, reason=f"不支持的内容类型：{ctype[:60]}")
    if len(body) > MAX_HTML_BYTES:
        return PageRead("failed", url, final, reason="页面过大")
    html = resp.text or ""
    head = html[:20000]
    marker = next((m for m in CHALLENGE_MARKERS if m in head), None)
    title, visible = _title_and_text(html)
    why = blocked_reason(final, title, visible)
    if why or (marker and len(visible) < 1500):
        return PageRead("blocked", url, final, title=title or None,
                        reason=f"HTTP 读取遇到验证/拦截（{why or '页面含 ' + marker}）")
    meta = extract_main_text(html, final)
    text = (meta.get("text") or "").strip()[:MAX_TEXT_CHARS]
    if len(text) < min_chars:
        return PageRead("no_content", url, final, title=meta.get("title") or title or None,
                        reason="HTTP 读取正文过短（可能需要执行脚本）")
    return PageRead("captured", url, final, title=meta.get("title") or title or None, text=text,
                    site_name=meta.get("sitename") or urlsplit(final).hostname, author=meta.get("author"),
                    publish_time_text=meta.get("date"),
                    meta={"via": "http", "ms": int((time.monotonic() - t0) * 1000),
                          "images": extract_images(html, final)})
