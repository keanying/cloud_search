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
