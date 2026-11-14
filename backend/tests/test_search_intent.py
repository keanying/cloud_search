"""按意图搜索：计划（语言/时效/站点）、改写无结果查询、模型挑选候选；DuckDuckGo 适配与引擎优先级。"""

from __future__ import annotations

import uuid

import pytest

from conftest import PAGES, quick_task_output, register, run_worker


async def _run_task(client, h, fake_llm, spec_patch: dict | None = None):
    out = quick_task_output()
    out["task_spec"]["limits"] = {"max_queries": 4, "max_sources": 1}
    out["task_spec"].update(spec_patch or {})
    fake_llm.compiler_outputs.append(out)
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "最近故宫开放时间有变化吗"})
    await run_worker()
    return (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]


async def test_intent_plan_refine_and_select(client, fake_llm, fake_browser):
    fake_llm.plan_output = {
        "intent": "用户想知道故宫近期开放时间是否调整（需要官方、最新信息）",
        "key_entities": ["故宫博物院"], "preferred_sources": ["dpm.org.cn"],
        "queries": [
            {"query": "site:dpm.org.cn 开放时间 公告", "purpose": "官方公告", "language": "zh", "recency": "month"},
            {"query": "\"故宫博物院\" 闭馆 调整 2026", "purpose": "近期调整", "language": "zh", "recency": "month"},
            {"query": "Palace Museum opening hours", "purpose": "英文来源", "language": "en"},
        ]}
    fake_browser.empty_queries = {"Palace Museum opening hours"}
    fake_llm.refine_output = [{"query": "Forbidden City visiting hours", "purpose": "改写", "language": "en"}]
    fake_llm.select_indices = [1]  # 两个候选、上限 1：模型选第 2 个
    h = await register(client)
    task = await _run_task(client, h, fake_llm, {"scope": {"questions": ["故宫开放时间"], "include_domains": []}})
    assert task["task_status"] == "completed", task
    submitted = {q.query: q for q in fake_browser.queries}
    assert submitted["site:dpm.org.cn 开放时间 公告"].recency == "month"
    assert submitted["Palace Museum opening hours"].language == "en"
    assert "Forbidden City visiting hours" in submitted  # 无结果的查询被改写后重搜
    assert "效果不好的查询" in fake_llm.prompts["search_planner"][1]
    assert fake_browser.reads == [list(PAGES)[1]]  # 只读了模型挑选的候选
    select_prompt = next(p for p in fake_llm.prompts["search_planner"] if "候选（编号" in p)
    assert "用户想知道故宫近期开放时间" in select_prompt  # 筛选时带上了意图


async def test_include_domains_get_site_queries(client, fake_llm, fake_browser):
    h = await register(client)
    await _run_task(client, h, fake_llm, {"scope": {"questions": ["故宫开放时间"], "include_domains": ["dpm.org.cn"],
                                                    "items": ["故宫博物院"]}})
    texts = [q.query for q in fake_browser.queries]
    assert any(t.startswith("site:dpm.org.cn") for t in texts)  # 用户指定站点必须被覆盖
    assert any("故宫博物院" in t for t in texts)


def test_ddg_urls_and_redirect_decoding():
    from cloudsearch.search.engines import ddg_search_url, decode_ddg_url

    u = ddg_search_url("故宫 开放时间", recency="week")
    assert u.startswith("https://duckduckgo.com/?") and "kl=cn-zh" in u and "df=w" in u
    assert "kl=wt-wt" in ddg_search_url("python asyncio", lang="en")
    assert ddg_search_url("x", html=True).startswith("https://html.duckduckgo.com/html/?")
    assert decode_ddg_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.dpm.org.cn%2FVisit.html&rut=abc") == \
        "https://www.dpm.org.cn/Visit.html"
    assert decode_ddg_url("https://example.com/a") == "https://example.com/a"


DDG_MAIN = """<html><body><ol>
<li data-layout="organic"><article data-testid="result">
  <h2><a data-testid="result-title-a" href="https://www.dpm.org.cn/Visit.html">导览 - 故宫博物院</a></h2>
  <div data-result="snippet">故宫博物院开放时间：旺季 8:30-17:00，周一闭馆。</div></article></li>
<li data-layout="organic"><article data-testid="result">
  <h2><a data-testid="result-title-a" href="https://example.cn/gugong">故宫开放时间 2026 最新</a></h2>
  <div data-result="snippet">故宫博物院开放时间与预约说明</div></article></li>
</ol>""" + "<p>pad</p>" * 200 + "</body></html>"
DDG_HTML = """<html><body>
<div class="result results_links web-result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.dpm.org.cn%2FVisit.html">导览 - 故宫博物院</a>
<a class="result__snippet">故宫博物院开放时间</a></div>
<div class="result result--ad"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">广告</a></div>
</body></html>"""


async def test_ddg_parsing_in_browser():
    """用真实浏览器执行解析脚本（无浏览器环境自动跳过）。"""
    from playwright.async_api import async_playwright

    from cloudsearch.browser.launch import resolve
    from cloudsearch.search.engines import DuckDuckGoEngine

    choice = resolve()
    if choice["mode"] in ("missing", "error"):
        pytest.skip("无可用浏览器")
    e = DuckDuckGoEngine()
    async with async_playwright() as p:
        b = await p.chromium.launch(**choice["launch_kwargs"])
        page = await b.new_page()
        await page.set_content(DDG_MAIN)
        rows = e._rows(await page.evaluate(e.JS))
        assert [r["url"] for r in rows] == ["https://www.dpm.org.cn/Visit.html", "https://example.cn/gugong"]
        assert "周一闭馆" in rows[0]["snippet"]
        await page.set_content(DDG_HTML)
        rows = e._rows(await page.evaluate(e.JS_HTML))
        assert [r["url"] for r in rows] == ["https://www.dpm.org.cn/Visit.html"]  # 解码跳转、过滤广告
        await b.close()


async def test_engine_priority_and_unreachable_cooldown(env, monkeypatch):
    """priority：DuckDuckGo 优先；网络不可达时换下一个引擎并冷却，后续查询不再等待它。"""
    import asyncio

    from cloudsearch.contracts import SearchHit, SearchQuery
    from cloudsearch.search import engines, service

    calls: list[str] = []

    class Down(engines.SearchEngine):
        name = "duckduckgo"

        async def search(self, s, query, n, *, lang=None, recency=None):
            calls.append(self.name)
            raise RuntimeError("Page.goto: net::ERR_CONNECTION_TIMED_OUT at https://duckduckgo.com/")

    class Up(engines.SearchEngine):
        name = "bing"

        async def search(self, s, query, n, *, lang=None, recency=None):
            calls.append(self.name)
            return [SearchHit(engine="bing", query=query, rank=1, url=f"https://a.cn/{len(calls)}",
                              title=f"{query} 官方"), SearchHit(engine="bing", query=query, rank=2,
                                                                url=f"https://b.cn/{len(calls)}", title=query)]

    monkeypatch.setattr(engines, "ENGINES", {"duckduckgo": Down(), "bing": Up()})
    monkeypatch.setattr(service, "ENGINES", {"duckduckgo": Down(), "bing": Up()})
    monkeypatch.setattr(asyncio, "sleep", lambda *_: asyncio.sleep.__wrapped__(0) if hasattr(asyncio.sleep, "__wrapped__") else _noop())
    service.health.reset()

    class S:
        lock = asyncio.Lock()

    rep = await service.browser_search(S(), [SearchQuery(query="故宫 开放时间"), SearchQuery(query="故宫 门票")])
    assert calls == ["duckduckgo", "bing", "bing"]  # 第二个查询不再尝试已冷却的 DuckDuckGo
    assert rep.unreachable_engines == ["duckduckgo"] and rep.per_query["故宫 门票"] == "bing"
    service.health.reset()


async def _noop():
    return None


# ---------------------------------------------------------------- 垂直来源
CUSTOM_PAGE = """<html><body><ul class="res">
<li class="r"><a class="t" href="/policy/1.html">关于博物馆开放管理的通知</a><p class="s">各地博物馆实行预约开放</p></li>
<li class="r"><a class="t" href="https://other.gov.cn/2">文旅部发布暑期参观指引</a><p class="s">暑期错峰</p></li>
</ul></body></html>"""


async def test_custom_source_from_config_parses_results(env, monkeypatch, tmp_path):
    from playwright.async_api import async_playwright

    from cloudsearch.browser.launch import resolve
    from cloudsearch.core import config
    from cloudsearch.search import service

    choice = resolve()
    if choice["mode"] in ("missing", "error"):
        pytest.skip("无可用浏览器")
    (tmp_path / "c.yaml").write_text("""
search:
  custom_sources:
    - name: gov_test
      label: 政府网测试
      description: 官方政策
      url: https://example.gov.cn/search?q={q}
      item: li.r
      link: a.t
      snippet: p.s
""", encoding="utf-8")
    monkeypatch.setenv("CS_CONFIG_FILE", str(tmp_path / "c.yaml"))
    config.get_settings.cache_clear()
    assert "gov_test" in service.vertical_sources() and "政府网测试" in service.describe_sources()
    src = service.all_engines()["gov_test"]

    class Sess:  # 只用到 page / goto / capture_frame
        def __init__(self, page):
            self.page = page

        async def goto(self, url, **kw):
            assert url == "https://example.gov.cn/search?q=%E5%8D%9A%E7%89%A9%E9%A6%86+%E5%BC%80%E6%94%BE"
            await self.page.set_content(CUSTOM_PAGE)

        async def capture_frame(self, **kw):
            pass

    async with async_playwright() as p:
        b = await p.chromium.launch(**choice["launch_kwargs"])
        page = await b.new_page()
        await page.goto("about:blank")
        hits = await src.search(Sess(page), "博物馆 开放", 5)
        await b.close()
    assert [h.title for h in hits] == ["关于博物馆开放管理的通知", "文旅部发布暑期参观指引"]
    assert hits[0].url.endswith("/policy/1.html") and hits[0].snippet == "各地博物馆实行预约开放"
    config.get_settings.cache_clear()


async def test_planner_source_validation(client, fake_llm, fake_browser):
    fake_llm.plan_output = {
        "intent": "了解故宫背景与公众号上的参观攻略", "key_entities": ["故宫博物院"], "preferred_sources": [],
        "queries": [
            {"query": "site:baike.baidu.com \"故宫博物院\"", "purpose": "百科", "language": "zh", "source": "baike"},
            {"query": "故宫 参观攻略", "purpose": "公众号", "language": "zh", "source": "weixin"},
            {"query": "故宫 开放时间", "purpose": "通用", "language": "zh", "source": "made_up_source"},
        ]}
    h = await register(client)
    await _run_task(client, h, fake_llm)
    by_purpose = {q.purpose: q for q in fake_browser.queries}
    assert by_purpose["百科"].source == "baike" and by_purpose["百科"].query == "故宫博物院"  # 站内搜索去掉语法
    assert by_purpose["公众号"].source == "weixin"
    assert by_purpose["通用"].source is None  # 未知来源 → 通用引擎
    assert "wikipedia_zh" in fake_llm.prompts["search_planner"][0]  # 规划时告知了可用来源


# ---------------------------------------------------------------- 人机验证识别与接管
BING_CHALLENGE = """<html><head><title>必应</title></head><body>
<h1>最后一步</h1><p>请解决以下难题以继续</p><label><input type="checkbox"> 请验证您是真人</label></body></html>"""
RESULTS_PAGE = """<html><head><title>搜索结果</title></head><body><ol id="b_results">
<li class="b_algo"><h2><a href="https://example.cn/a">如何关闭网站验证码功能</a></h2><p>验证码设置教程……</p></li>
</ol>""" + "<p>x</p>" * 300 + "</body></html>"


async def test_challenge_page_detection():
    from playwright.async_api import async_playwright

    from cloudsearch.browser.launch import resolve
    from cloudsearch.search.engines import page_is_challenge

    choice = resolve()
    if choice["mode"] in ("missing", "error"):
        pytest.skip("无可用浏览器")

    class Sess:
        def __init__(self, page):
            self.page = page
            self.challenge_reason = None

    async with async_playwright() as p:
        b = await p.chromium.launch(**choice["launch_kwargs"])
        page = await b.new_page()
        await page.set_content(BING_CHALLENGE)
        assert await page_is_challenge(Sess(page)) is True  # 用户截图中的必应验证页
        await page.set_content('<div class="cf-turnstile" style="width:300px;height:65px"></div><p>Checking</p>')
        assert await page_is_challenge(Sess(page)) is True  # 可见的验证组件（真实 Turnstile 约 300×65）
        await page.set_content('<div class="cf-turnstile" style="display:none"></div><p>' + '正文' * 100 + '</p>')
        assert await page_is_challenge(Sess(page)) is False  # 隐藏的组件不算
        await page.set_content(RESULTS_PAGE)
        # 结果页可能含“验证码”字样：引擎实现只在“没有解析到结果”时才做文字判断，避免误判
        await b.close()


async def test_blocked_engine_requests_takeover_then_retries(env, monkeypatch):
    import asyncio

    from cloudsearch.contracts import SearchHit, SearchQuery
    from cloudsearch.search import engines, service

    state = {"calls": 0, "handoffs": []}

    class Bing(engines.SearchEngine):
        name = "bing"

        async def search(self, s, query, n, *, lang=None, recency=None):
            state["calls"] += 1
            if state["calls"] == 1:
                raise engines.EngineBlocked("bing")
            return [SearchHit(engine="bing", query=query, rank=1, url="https://a.cn/1", title=query),
                    SearchHit(engine="bing", query=query, rank=2, url="https://a.cn/2", title=query)]

    monkeypatch.setattr(service, "ENGINES", {"bing": Bing()})
    monkeypatch.setenv("CS_SEARCH_ENGINES", '["bing"]')
    from cloudsearch.core import config

    config.get_settings.cache_clear()
    service.health.reset()

    async def on_blocked(sess, reason):
        state["handoffs"].append(reason)
        return True  # 用户完成了验证

    class S:
        lock = asyncio.Lock()

    rep = await service.browser_search(S(), [SearchQuery(query="故宫 开放时间")], on_blocked=on_blocked)
    assert state["handoffs"] and "人机验证" in state["handoffs"][0]
    assert state["calls"] == 2 and len(rep.hits) == 2 and rep.blocked_engines == []
    service.health.reset()
    config.get_settings.cache_clear()
