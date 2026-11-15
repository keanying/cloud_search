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


async def test_search_tries_all_http_methods_before_browser(env, monkeypatch):
    """先用所有不开浏览器的方式（duckduckgo-mcp-server → ddgs），都失败才打开浏览器搜索。"""
    import asyncio

    from cloudsearch.contracts import SearchHit, SearchQuery
    from cloudsearch.search import engines, service

    calls: list[str] = []

    class Ddg(engines.SearchEngine):
        name = "duckduckgo"

        async def search(self, s, query, n, *, lang=None, recency=None, via=None):
            calls.append(f"duckduckgo:{via}")
            if via == "http":
                raise engines.EngineUnavailable("duckduckgo（HTTP）被拦截：HTTP 202")
            return [SearchHit(engine="duckduckgo", query=query, rank=1, url="https://a.cn/1", title=query)]

    class Ddgs(engines.SearchEngine):
        name, http_only = "ddgs", True

        async def search(self, s, query, n, *, lang=None, recency=None):
            calls.append("ddgs")
            return []

    class Bing(engines.SearchEngine):
        name = "bing"

        async def search(self, s, query, n, *, lang=None, recency=None):
            calls.append("bing")
            return [SearchHit(engine="bing", query=query, rank=1, url="https://b.cn/1", title=query)]

    reg = {"duckduckgo": Ddg(), "ddgs": Ddgs(), "bing": Bing()}
    monkeypatch.setattr(service, "ENGINES", reg)
    monkeypatch.setattr(service, "vertical_sources", lambda: {})
    monkeypatch.setattr(service.random, "uniform", lambda *_: 0)
    from cloudsearch.core.config import get_settings

    monkeypatch.setattr(get_settings(), "search_engines", ["duckduckgo", "bing", "ddgs"])
    service.health.reset()
    assert service.search_plan(["duckduckgo", "bing", "ddgs"]) == [
        ("duckduckgo", "http"), ("ddgs", None), ("duckduckgo", "browser"), ("bing", None)]

    class S:
        lock = asyncio.Lock()
        challenge_reason = None

    rep = await service.browser_search(S(), [SearchQuery(query="故宫 开放时间")])
    # bing 虽然排在 ddgs 前面，但它要开浏览器，所以排在所有 HTTP 方式之后
    assert calls == ["duckduckgo:http", "ddgs", "duckduckgo:browser"]
    assert rep.per_query["故宫 开放时间"] == "duckduckgo" and rep.unreachable_engines == ["duckduckgo"]
    # HTTP 方式冷却不影响浏览器方式
    assert service.health.available(["duckduckgo", "duckduckgo@browser"]) == ["duckduckgo@browser"]
    monkeypatch.setattr(get_settings(), "search_ddg_backend", "browser")
    assert service.search_plan(["duckduckgo", "ddgs"]) == [("ddgs", None), ("duckduckgo", "browser")]
    service.health.reset()


ARTICLE = ("<html><head><title>故宫博物院开放时间</title></head><body><nav>首页 导航</nav><article><h1>故宫博物院开放时间</h1>"
           + "".join(f"<p>第{i}段：故宫博物院实行预约参观，每周一闭馆（法定节假日除外），旺季 8:30 开放，16:10 停止入院。</p>"
                     for i in range(8)) + "</article></body></html>")


class _Resp:
    def __init__(self, status, text="", headers=None, content=None):
        self.status_code, self.text, self.headers = status, text, headers or {"content-type": "text/html; charset=utf-8"}
        self.content = content if content is not None else text.encode()


def _fake_session(monkeypatch, routes, seen):
    import curl_cffi.requests as cr

    class Sess:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            seen.append(url)
            assert kw.get("allow_redirects") is False  # 重定向由我们逐跳检查
            return routes[url]

    monkeypatch.setattr(cr, "AsyncSession", Sess)


async def test_http_reader_extracts_article_and_follows_checked_redirects(env, monkeypatch):
    from cloudsearch.browser import http_reader

    checked, seen = [], []

    async def check(url):
        checked.append(url)

    monkeypatch.setattr(http_reader, "check_url", check)
    _fake_session(monkeypatch, {
        "https://t.cn/a": _Resp(302, headers={"location": "https://www.dpm.org.cn/visit.html"}),
        "https://www.dpm.org.cn/visit.html": _Resp(200, ARTICLE)}, seen)
    r = await http_reader.read_http("https://t.cn/a")
    assert r.status == "captured" and r.final_url == "https://www.dpm.org.cn/visit.html"
    assert "每周一闭馆" in r.text and "导航" not in r.text and r.meta["via"] == "http"
    assert checked == ["https://t.cn/a", "https://www.dpm.org.cn/visit.html"]  # 每一跳都做出口检查


async def test_http_reader_reports_block_short_and_guard(env, monkeypatch):
    from cloudsearch.browser import guard, http_reader

    async def check(url):
        if "10.0.0.1" in url:
            raise guard.UrlNotAllowed("目标地址不在允许的公网范围: 10.0.0.1")

    monkeypatch.setattr(http_reader, "check_url", check)
    cf = "<html><head><title>Just a moment...</title></head><body>Checking your browser before accessing.</body></html>"
    _fake_session(monkeypatch, {
        "https://cf.example/x": _Resp(403, cf),
        "https://cf2.example/x": _Resp(200, cf),
        "https://spa.example/": _Resp(200, "<html><body><div id=app></div><script>render()</script></body></html>"),
        "https://r.example/": _Resp(301, headers={"location": "http://10.0.0.1/admin"}),
        "https://bin.example/f.zip": _Resp(200, "PK", headers={"content-type": "application/zip"})}, [])
    assert (await http_reader.read_http("https://cf.example/x")).status == "blocked"
    assert (await http_reader.read_http("https://cf2.example/x")).status == "blocked"
    assert (await http_reader.read_http("https://spa.example/")).status == "no_content"  # 需要执行脚本 → 交给浏览器
    r = await http_reader.read_http("https://r.example/")
    assert r.status == "failed" and "UrlNotAllowed" in r.reason  # 重定向到内网被拦
    assert (await http_reader.read_http("https://bin.example/f.zip")).status == "failed"


def test_source_title_and_site_tidy():
    from cloudsearch.search.source_names import tidy

    assert tidy("黄仁勋走了，“达链”老板们开始盘订单_腾讯新闻", "Copyright 1998 - 2026 Tencent. All Rights Reserved",
                "https://news.qq.com/a/1") == ("黄仁勋走了，“达链”老板们开始盘订单", "腾讯新闻")
    assert tidy("巨头算力订单拉动数据中心扩张，AI基建融资路径迎检验 - 21世纪经济报道", "sfccn.com",
                "https://www.sfccn.com/x") == ("巨头算力订单拉动数据中心扩张，AI基建融资路径迎检验", "21世纪经济报道")
    assert tidy("PEP 8 – Style Guide for Python Code | peps.python.org", "peps.python.org",
                "https://peps.python.org/pep-0008/") == ("PEP 8 – Style Guide for Python Code", "peps.python.org")
    assert tidy("GPT-5 发布", None, "https://www.example.com/a") == ("GPT-5 发布", "example.com")  # 不拆连字符
    assert tidy(None, "©2026 某某网 版权所有", "https://www.foo.cn/") == (None, "foo.cn")


def test_pdf_title_and_missing_notes():
    from cloudsearch.browser.reader import pdf_title
    from cloudsearch.contracts import FieldSpec
    from cloudsearch.orchestrator.exporters import missing_text
    from cloudsearch.search.source_names import tidy

    assert pdf_title(b"", "[第1页]\nLecture Notes on Lisp Machines\n", "https://ocw.mit.edu/30eb0d06f5903c7a4256d397a.pdf") \
        == "Lecture Notes on Lisp Machines"
    assert tidy("30eb0d06f5903c7a4256d397a", None, "https://ocw.mit.edu/x.pdf")[0] is None
    fields = [FieldSpec(key="price", label="票价"), FieldSpec(key="phone", label="电话"), FieldSpec(key="open", label="开放时间")]
    assert missing_text(fields, {"price": "not_found", "phone": "not_found", "open": "source_conflict"}) \
        == "来源未提及：票价、电话；来源冲突：开放时间"
