"""测试夹具：临时 SQLite + 本地存储；八个角色注入 FunctionModel（不触网、不计费）；浏览器用假实现。"""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"


@pytest.fixture
async def env(tmp_path, monkeypatch):
    # 默认 SQLite；设置 CS_TEST_DATABASE_URL 可在 MySQL 8 上运行同一套测试（每个用例重建表）
    mysql_url = os.environ.get("CS_TEST_DATABASE_URL")
    monkeypatch.setenv("CS_DATABASE_URL", mysql_url or f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("CS_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("CS_EMBEDDED_WORKER", "false")
    monkeypatch.setenv("CS_CONFIG_FILE", str(tmp_path / "config.yaml"))  # 测试不读取开发者本地 config.yaml
    monkeypatch.setenv("CS_BROWSER_FRAME_INTERVAL_S", "0")
    from cloudsearch.core import config, storage
    from cloudsearch.db import base

    config.get_settings.cache_clear()
    storage._storage = None
    await base.dispose_engine()
    if mysql_url:
        from cloudsearch.db import models  # noqa: F401

        async with base.get_engine().begin() as conn:
            await conn.run_sync(base.Base.metadata.drop_all)
    await base.create_all()
    yield
    from cloudsearch.llm.registry import clear_model_overrides

    clear_model_overrides()
    await base.dispose_engine()
    config.get_settings.cache_clear()


@pytest.fixture
async def client(env):
    from cloudsearch.app import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


class AuthHeaders(dict):
    user: dict


async def register(client, name="alice") -> AuthHeaders:
    r = await client.post("/api/v1/auth/register", json={"username": name, "password": "secret123"})
    assert r.status_code == 201, r.text
    data = r.json()
    h = AuthHeaders({"Authorization": f"Bearer {data['access_token']}"})
    h.user = data["user"]
    return h


# ---------------------------------------------------------------- 假模型
@dataclass
class FakeLLM:
    calls: dict[str, int] = field(default_factory=dict)
    compiler_outputs: list[dict] = field(default_factory=list)
    writer_markdown: str = "故宫每周一闭馆[1]。这是一句不存在来源的引用[9]。"
    gate: asyncio.Event | None = None  # 设定后，report_writer 调用前会等待
    prompts: dict[str, list[str]] = field(default_factory=dict)
    # search_planner：计划 / 筛选 / 改写 三种输出
    plan_output: dict = field(default_factory=lambda: {
        "intent": "了解故宫开放时间", "key_entities": ["故宫博物院"], "preferred_sources": ["dpm.org.cn"],
        "queries": [{"query": "故宫 开放时间", "purpose": "开放时间", "language": "zh"}]})
    select_indices: list[int] | None = None  # None = 全选
    refine_output: list[dict] = field(default_factory=list)

    def _model(self, role: str, builder):
        async def fn(messages, info: AgentInfo):
            self.calls[role] = self.calls.get(role, 0) + 1
            prompt = "\n".join(str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", []))
            props = info.output_tools[0].parameters_json_schema.get("properties", {}) if info.output_tools else {}
            self.prompts.setdefault(role, []).append(prompt)
            args = builder(prompt, props) if role == "search_planner" else builder(prompt)
            if role == "report_writer" and self.gate is not None:
                await self.gate.wait()
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

        return FunctionModel(fn)

    def _planner(self, prompt: str, props: dict) -> dict:
        if "selected" in props:
            n = len([ln for ln in prompt.split("候选（编号", 1)[-1].splitlines() if " | " in ln])
            idx = list(range(n)) if self.select_indices is None else self.select_indices
            return {"selected": [{"index": i, "reason": "相关"} for i in idx]}
        if "intent" in props:
            return self.plan_output
        return {"queries": self.refine_output}

    def install(self):
        from cloudsearch.llm.registry import set_model_override

        def compiler(prompt: str) -> dict:
            if self.compiler_outputs:
                return self.compiler_outputs.pop(0)
            return {"kind": "chat", "reply": "你好！有什么可以帮你？", "conversation_title": "问候"}

        def extractor(prompt: str) -> dict:
            text = prompt.split("正文开始>>>", 1)[-1].split("<<<正文结束", 1)[0].strip()
            sentence = re.split(r"[。\n]", text)[0] + "。"
            out = {"relevant": True, "findings": [{"claim": "开放安排", "quote": sentence, "aspect": "开放时间"}],
                   "records": []}
            if "需要抽取的字段" in prompt:
                m = re.search(r"名称[:：](\S+?)[，,]", text)
                price = re.search(r"票价[:：](\S+?)元", text)
                out["records"] = [{"entity_name": m.group(1) if m else "未知",
                                   "values": {"name": m.group(1) if m else None,
                                              "price": price.group(1) if price else None,
                                              "note": "=1+1" if m else None},
                                   "quotes": {"name": m.group(0) if m else "", "price": price.group(0) if price else "",
                                              "note": "这段话不在原文里"},
                                   "missing_reasons": {}}]
            return out

        roles = {
            "requirement_compiler": compiler,
            "search_planner": self._planner,
            "coordinator": lambda p: {"sufficient": True, "missing_aspects": [], "extra_queries": []},
            "browser_researcher": lambda p: {"action": "finish", "reason": "ok"},
            "extractor": extractor,
            "verifier": lambda p: {"conflicts": [], "unsupported": []},
            "analyst": lambda p: {"analyses": [{"title": "数量", "description": "记录数",
                                                "metrics": [{"func": "count", "alias": "数量"}]}]},
            "report_writer": lambda p: {"title": "故宫开放时间", "markdown": self.writer_markdown, "limitations": []},
        }
        for role, b in roles.items():
            set_model_override(role, self._model(role, b))
        return self


@pytest.fixture
def fake_llm(env):
    return FakeLLM().install()


# ---------------------------------------------------------------- 假浏览器
PAGES = {
    "https://a.example.com/1": "故宫博物院每周一闭馆，法定节假日除外。名称：故宫博物院，票价：60元。更多介绍内容。" * 3,
    "https://b.example.com/2": "国家博物馆周二至周日开放，周一闭馆。名称：国家博物馆，票价：0元。其他信息。" * 3,
}


@dataclass
class FakeBrowser:
    read_gate: asyncio.Event | None = None
    reads: list[str] = field(default_factory=list)
    queries: list = field(default_factory=list)       # 实际提交的搜索（SearchQuery）
    empty_queries: set[str] = field(default_factory=set)  # 这些查询返回无结果


@pytest.fixture
def fake_browser(env, monkeypatch):
    from cloudsearch.browser.reader import PageRead
    from cloudsearch.contracts import SearchHit
    from cloudsearch.core.ids import new_id
    from cloudsearch.db.base import session_scope
    from cloudsearch.db.models import BrowserSession
    from cloudsearch.orchestrator import pipeline
    from cloudsearch.search.service import SearchReport, normalize_url

    fb = FakeBrowser()

    class FakeSession:
        def __init__(self, bsid):
            self.browser_session_id = bsid
            self.lock = asyncio.Lock()

    class FakePool:
        @asynccontextmanager
        async def session(self, *, project_id, task_id, run_id, worker_id, label):
            bsid = new_id("bs")
            async with session_scope() as s:
                s.add(BrowserSession(browser_session_id=bsid, project_id=project_id, task_id=task_id, run_id=run_id,
                                     worker_id=worker_id, session_label=label, session_status="active"))
            yield FakeSession(bsid)
            async with session_scope() as s:
                (await s.get(BrowserSession, bsid)).session_status = "closed"

    async def fake_search(sess, queries, *, per_query=None, exclude_domains=None, before_each=None, on_blocked=None):
        rep = SearchReport()
        for raw in queries:
            q = getattr(raw, "query", raw)
            fb.queries.append(raw)
            if before_each:
                await before_each()
            urls = [] if q in fb.empty_queries else list(PAGES)
            for i, url in enumerate(urls):
                if any(normalize_url(url) == normalize_url(h.url) for h in rep.hits):
                    continue
                rep.hits.append(SearchHit(engine="fake", query=q, rank=i + 1, url=url, title=f"页面{i + 1}"))
            rep.per_query[q] = "fake" if urls else "无结果"
            rep.hit_counts[q] = len(urls)
        return rep

    async def fake_read(sess, url, *, goal, ctx, allow_interaction=True, on_blocked=None):
        await ctx.check()
        fb.reads.append(url)
        if fb.read_gate is not None:
            await fb.read_gate.wait()
        return PageRead("captured", url, url, title=f"标题 {url}", text=PAGES[url], site_name="example.com")

    monkeypatch.setattr(pipeline, "get_pool", lambda: FakePool())
    monkeypatch.setattr(pipeline, "browser_search", fake_search)
    monkeypatch.setattr(pipeline, "read_source", fake_read)
    return fb


def quick_task_output(mode="quick_search", needs_confirmation=False, dataset=None) -> dict:
    spec = {"mode": mode, "title": "故宫开放时间", "requirement_text": "故宫什么时候开放？",
            "scope": {"questions": ["故宫什么时候开放？"]}, "limits": {"max_queries": 2, "max_sources": 2}}
    if dataset:
        spec["dataset"] = dataset
    return {"kind": "task", "reply": "我来搜索一下。", "conversation_title": "故宫开放时间", "task_spec": spec,
            "needs_confirmation": needs_confirmation, "plan_steps": ["搜索", "读取", "回答"]}


async def run_worker():
    from cloudsearch.worker.main import Worker

    w = Worker("w-test")
    await w.tick()
    await w.drain()
    return w


def parts_of(msg: dict, type_: str) -> list[dict]:
    return [p for p in msg["parts"] if p["type"] == type_]


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False)
