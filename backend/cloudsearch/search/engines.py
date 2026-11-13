"""浏览器搜索引擎适配器：用云端浏览器打开搜索引擎页面并解析结果，不使用搜索 API。

- 遇到验证码/安全验证/空白页：抛 EngineBlocked，由调用方冷却该引擎并换下一个，绝不尝试破解。
- 结果链接可能是跳转链接（百度/搜狗 link?url=），由读取阶段跟随并记录最终 URL。
- 搜索结果的标题/摘要只是发现线索，不作为证据。
"""

from __future__ import annotations

import base64
import random
import re
from urllib.parse import parse_qs, quote_plus, urlsplit

from ..browser.pool import CloudBrowserSession
from ..contracts import SearchHit


class EngineBlocked(Exception):
    pass


GENERIC_JS = r"""(engineHost) => {
  const out = []; const seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const t = (a.textContent || '').trim().replace(/\s+/g, ' ');
    if (t.length < 8 || t.length > 120) continue;
    let h; try { h = new URL(a.href); } catch (e) { continue; }
    if (!/^https?:$/.test(h.protocol) || h.hostname.endsWith(engineHost)) continue;
    if (seen.has(h.href)) continue; seen.add(h.href);
    out.push({url: h.href, title: t, snippet: null});
  }
  return out.slice(0, 20);
}"""


def _clean(text: str | None, n: int = 300) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n] or None


def _grams(text: str) -> set[str]:
    """中文按二字组、其他按单词切分，用于粗略相关性判断。"""
    text = text.lower()
    out = set(re.findall(r"[a-z0-9]{2,}", text))
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        out.update(seg[i:i + 2] for i in range(len(seg) - 1)) if len(seg) > 1 else out.add(seg)
    return out


def looks_relevant(query: str, hits: list[SearchHit]) -> bool:
    """诱饵结果检测：前 5 条中至少 2 条（结果少于 3 条时至少 1 条）覆盖查询词约三分之一以上，
    否则视为无效结果页（例如被风控时返回的无关热门内容），换下一个引擎。"""
    if not hits:
        return False
    q = _grams(query)
    if not q:
        return True
    top = hits[:5]

    def covered(h: SearchHit) -> bool:
        g = _grams(f"{h.title or ''} {h.snippet or ''}")
        return len(q & g) / len(q) >= 0.34

    need = 2 if len(top) >= 3 else 1
    return sum(1 for h in top if covered(h)) >= need


class SearchEngine:
    name = "base"
    host = ""

    async def search(self, s: CloudBrowserSession, query: str, n: int) -> list[SearchHit]:
        raise NotImplementedError

    async def _blocked(self, s: CloudBrowserSession, patterns: str) -> bool:
        url = s.page.url
        if re.search(patterns, url, re.I):
            return True
        try:
            html_len = await s.page.evaluate("() => document.documentElement.outerHTML.length")
            text = await s.page.evaluate("() => (document.body ? document.body.innerText : '').slice(0, 600)")
        except Exception:  # noqa: BLE001
            return True
        if html_len < 1000:
            return True
        return bool(re.search(r"安全验证|验证码|异常访问|captcha|unusual traffic|请输入验证码|人机验证", text, re.I))

    def _hits(self, query: str, rows: list[dict], n: int) -> list[SearchHit]:
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for r in rows:
            url = r.get("url")
            if not url or not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            hits.append(SearchHit(engine=self.name, query=query, rank=len(hits) + 1, url=url,
                                  title=_clean(r.get("title"), 200), snippet=_clean(r.get("snippet"))))
            if len(hits) >= n:
                break
        return hits


def decode_bing_url(href: str) -> str:
    """必应 /ck/a?...&u=a1<base64url> 跳转链接解码为原始 URL。"""
    try:
        parts = urlsplit(href)
        if parts.hostname and parts.hostname.endswith("bing.com") and parts.path.startswith("/ck/"):
            u = parse_qs(parts.query).get("u", [""])[0]
            if u.startswith("a1"):
                raw = u[2:]
                raw += "=" * (-len(raw) % 4)
                return base64.urlsafe_b64decode(raw).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        pass
    return href


class BingEngine(SearchEngine):
    name, host = "bing", "bing.com"
    JS = r"""() => Array.from(document.querySelectorAll('#b_results > li.b_algo')).map(li => {
        const a = li.querySelector('h2 a');
        const p = li.querySelector('.b_caption p, p.b_lineclamp2, p.b_lineclamp3, p.b_lineclamp4, .b_algoSlug');
        return {url: a && a.href, title: a && a.textContent, snippet: p && p.textContent};
    })"""

    async def search(self, s: CloudBrowserSession, query: str, n: int) -> list[SearchHit]:
        # 通过首页输入框搜索（直接拼 URL 在部分网络下会被重定向回首页）
        await s.goto("https://cn.bing.com/", activity=f"必应搜索：{query}", check=False, wait_until="load")
        box = s.page.locator("#sb_form_q").first
        await box.click(timeout=8000)
        await box.fill("")
        await box.type(query, delay=random.randint(40, 90))
        await s.page.keyboard.press("Enter")
        try:
            await s.page.wait_for_selector("#b_results > li.b_algo", state="attached", timeout=12000)
        except Exception:  # noqa: BLE001
            pass
        await s.capture_frame(force=True)
        if await self._blocked(s, r"/captcha|challenge"):
            raise EngineBlocked("bing")
        rows = await s.page.evaluate(self.JS)
        for r in rows:
            if r.get("url"):
                r["url"] = decode_bing_url(r["url"])
        if not rows:
            rows = await s.page.evaluate(GENERIC_JS, self.host)
        return self._hits(query, rows, n)


class BaiduEngine(SearchEngine):
    name, host = "baidu", "baidu.com"
    JS = r"""() => {
      const blocks = document.querySelectorAll('#content_left > div[mu], #content_left .result, #content_left .c-container');
      const out = [];
      for (const b of blocks) {
        const a = b.querySelector('h3 a') || b.querySelector('a[href]');
        if (!a) continue;
        let mu = b.getAttribute('mu') || '';
        if (!/^https?:/.test(mu) || /nourl/.test(mu)) mu = '';
        const h3 = b.querySelector('h3');
        const title = (h3 || a).textContent;
        const snip = b.querySelector('[class*="content-right"], [class*="abstract"], .c-span-last, [data-module="abstract"]');
        out.push({url: mu || a.href, title, snippet: snip ? snip.textContent : (b.textContent || '').slice(0, 300)});
      }
      return out;
    }"""

    async def search(self, s: CloudBrowserSession, query: str, n: int) -> list[SearchHit]:
        await s.goto(f"https://www.baidu.com/s?wd={quote_plus(query)}&rn=20", activity=f"百度搜索：{query}",
                     check=False, wait_until="load")
        try:
            await s.page.wait_for_selector("#content_left", state="attached", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        await s.capture_frame(force=True)
        if await self._blocked(s, r"wappass|captcha|verify"):
            raise EngineBlocked("baidu")
        rows = await s.page.evaluate(self.JS)
        if not rows:
            rows = await s.page.evaluate(GENERIC_JS, self.host)
        return self._hits(query, rows, n)


class SogouEngine(SearchEngine):
    name, host = "sogou", "sogou.com"
    JS = r"""() => Array.from(document.querySelectorAll('.results .vrwrap, .results .rb')).map(b => {
        const a = b.querySelector('h3 a');
        const p = b.querySelector('.str-info, .str_info, .space-txt, .text-layout, p');
        return {url: a && a.href, title: a && a.textContent, snippet: p && p.textContent};
    })"""

    async def search(self, s: CloudBrowserSession, query: str, n: int) -> list[SearchHit]:
        await s.goto(f"https://www.sogou.com/web?query={quote_plus(query)}", activity=f"搜狗搜索：{query}",
                     check=False, wait_until="load")
        await s.capture_frame(force=True)
        if await self._blocked(s, r"antispider|/captcha"):
            raise EngineBlocked("sogou")
        rows = await s.page.evaluate(self.JS)
        if not rows:
            rows = await s.page.evaluate(GENERIC_JS, self.host)
        return self._hits(query, rows, n)


ENGINES: dict[str, SearchEngine] = {e.name: e for e in (BingEngine(), BaiduEngine(), SogouEngine())}
