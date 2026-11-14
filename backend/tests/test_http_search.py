"""DuckDuckGo HTTP 接口（参考 duckduckgo-mcp-server）与 ddgs 聚合：解析、拦截回退链、限流重试、浏览器兜底。"""

from __future__ import annotations

import pytest

DDG_PAGE = """<html><body><div class="serp__results">
<div class="result results_links result--ad"><h2 class="result__title"><a class="result__a"
  href="https://duckduckgo.com/y.js?ad_domain=x">广告</a></h2></div>
<div class="result results_links web-result"><h2 class="result__title"><a class="result__a"
  href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.dpm.org.cn%2Fvisit.html&amp;rut=abc">故宫博物院 开放时间</a></h2>
  <a class="result__snippet" href="#">故宫博物院每周一闭馆（法定节假日除外）。</a></div>
<div class="result results_links web-result"><h2 class="result__title"><a class="result__a"
  href="https://baike.baidu.com/item/故宫">故宫 百度百科</a></h2><a class="result__snippet">北京故宫…</a></div>
</div></body></html>"""


async def _stub_searcher(monkeypatch, httpx_result, curl_result=None):
    """只替换 duckduckgo-mcp-server 的网络请求，保留它自己的回退判断、解析、去广告逻辑。"""
    from cloudsearch.search import http_engines as he

    he._searcher = None
    searcher = he._make_searcher()
    calls = []

    async def fake_httpx(data):
        calls.append(("httpx", dict(data)))
        return httpx_result

    async def fake_curl(data):
        calls.append(("curl", dict(data)))
        if isinstance(curl_result, Exception):
            raise curl_result
        return curl_result

    monkeypatch.setattr(searcher, "_request_httpx", fake_httpx)
    monkeypatch.setattr(searcher, "_request_curl", fake_curl)
    return calls


async def test_ddg_uses_duckduckgo_mcp_server(env, monkeypatch):
    from duckduckgo_mcp_server.server import DuckDuckGoSearcher

    from cloudsearch.search import http_engines as he

    calls = await _stub_searcher(monkeypatch, (200, DDG_PAGE))
    rows = await he.ddg_http_search("故宫 开放时间", 5, lang="zh", recency="month")
    assert isinstance(he._searcher, DuckDuckGoSearcher)  # 用的是上游库
    assert [r["url"] for r in rows] == ["https://www.dpm.org.cn/visit.html", "https://baike.baidu.com/item/故宫"]
    assert rows[0]["title"] == "故宫博物院 开放时间" and "周一闭馆" in rows[0]["snippet"]
    assert calls == [("httpx", {"q": "故宫 开放时间", "b": "", "kl": "cn-zh", "kp": "-1", "df": "m"})]


async def test_ddg_library_falls_back_to_curl_then_reports_block(env, monkeypatch):
    from cloudsearch.search import http_engines as he

    calls = await _stub_searcher(monkeypatch, (202, "<html>anomaly</html>"), DDG_PAGE)
    assert len(await he.ddg_http_search("故宫", 5)) == 2
    assert [c[0] for c in calls] == ["httpx", "curl"]  # 上游 auto：202 被拦 → curl_cffi 重试

    await _stub_searcher(monkeypatch, (202, ""), "<html>still blocked</html>")
    with pytest.raises(he.HttpBlocked, match="没有返回结果"):
        await he.ddg_http_search("故宫", 5)

    await _stub_searcher(monkeypatch, (202, ""), RuntimeError("curl boom"))
    with pytest.raises(he.HttpBlocked, match="curl boom"):
        await he.ddg_http_search("故宫", 5)


def test_proxy_passed_to_library_clients(env, monkeypatch):
    from cloudsearch.core.config import get_settings
    from cloudsearch.search import http_engines as he

    monkeypatch.setattr(get_settings(), "browser_proxy", "http://127.0.0.1:7890")
    he._searcher = None
    a = he._make_searcher()
    assert he._make_searcher() is a  # 缓存
    monkeypatch.setattr(get_settings(), "browser_proxy", None)
    assert he._make_searcher() is not a  # 代理变化后重建
    he._searcher = None


async def test_duckduckgo_engine_http_first_then_browser(env, monkeypatch):
    from cloudsearch.core.config import get_settings
    from cloudsearch.search import engines, http_engines as he

    class Sess:
        challenge_reason = None

        async def set_activity(self, a):
            self.activity = a

    eng = engines.DuckDuckGoEngine()

    async def ok(q, n, lang=None, recency=None):
        return [{"url": "https://www.dpm.org.cn/visit.html", "title": "故宫博物院 开放时间", "snippet": "周一闭馆"}]

    monkeypatch.setattr(he, "ddg_http_search", ok)
    hits = await eng.search(Sess(), "故宫 开放时间", 5, lang="zh")
    assert hits[0].url == "https://www.dpm.org.cn/visit.html" and hits[0].engine == "duckduckgo"

    async def blocked(q, n, lang=None, recency=None):
        raise he.HttpBlocked("HTTP 202")

    browser_called = []

    async def browser(self, s, q, n, lang=None, recency=None):
        browser_called.append(q)
        return []

    monkeypatch.setattr(he, "ddg_http_search", blocked)
    monkeypatch.setattr(engines.DuckDuckGoEngine, "_browser_search", browser)
    assert await eng.search(Sess(), "故宫", 5) == [] and browser_called == ["故宫"]  # auto：退回浏览器
    monkeypatch.setattr(get_settings(), "search_ddg_backend", "http")
    with pytest.raises(engines.EngineUnavailable, match="HTTP 202"):
        await eng.search(Sess(), "故宫", 5)  # 仅 HTTP：按不可达冷却


async def test_ddgs_engine(env, monkeypatch):
    from cloudsearch.search import engines, http_engines as he

    class Sess:
        async def set_activity(self, a):
            pass

    async def rows(q, n, lang=None, recency=None):
        return [{"url": "https://www.mojeek.com/x", "title": "T", "snippet": "S"}, {"url": "ftp://bad", "title": "x"}]

    monkeypatch.setattr(he, "ddgs_search", rows)
    hits = await engines.DdgsEngine().search(Sess(), "q", 5)
    assert [h.url for h in hits] == ["https://www.mojeek.com/x"] and hits[0].engine == "ddgs"

    async def boom(q, n, lang=None, recency=None):
        raise RuntimeError("Ratelimit")

    monkeypatch.setattr(he, "ddgs_search", boom)
    with pytest.raises(engines.EngineUnavailable):
        await engines.DdgsEngine().search(Sess(), "q", 5)
    assert "ddgs" in engines.ENGINES


def test_chrome_error_page_is_network_error():
    from cloudsearch.browser.pool import BrowserNetworkError
    from cloudsearch.search.engines import is_network_error

    assert is_network_error(BrowserNetworkError("net::ERR_EMPTY_RESPONSE 打开 https://www.baidu.com 失败"))
