"""模型能力自适应（真实 OpenAI 客户端 + 模拟供应方）与旧库自动迁移。

模拟服务器复现 DeepSeek 思考模式：收到 tool_choice=required 返回
400 "Thinking mode does not support this tool_choice"。
"""

from __future__ import annotations

import json
import socket
import threading
import time
import uuid

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from conftest import parts_of, register, run_worker


def _answer_for(schema: dict) -> dict:
    props = (schema or {}).get("properties", {})
    if "kind" in props:
        return {"kind": "chat", "reply": "你好，我是测试模型。", "conversation_title": "问候"}
    if "number" in props:
        return {"status": "ok", "number": 42}
    return {}


def make_provider(mode: str) -> tuple[FastAPI, dict]:
    """mode=thinking：拒绝 tool_choice=required；mode=no_tools：拒绝任何 tools。"""
    app = FastAPI()
    seen: dict = {"tool_choice": [], "requests": 0}

    @app.post("/v1/chat/completions")
    async def chat(req: Request):
        body = await req.json()
        seen["requests"] += 1
        tools = body.get("tools") or []
        seen["tool_choice"].append(body.get("tool_choice"))
        if mode == "thinking" and body.get("tool_choice") == "required":
            return JSONResponse(status_code=400, content={"error": {
                "message": "Thinking mode does not support this tool_choice (request_id: x)",
                "type": "invalid_request_error", "param": None, "code": "invalid_request_error"}})
        if mode == "no_tools" and tools:
            return JSONResponse(status_code=400, content={"error": {
                "message": "This model does not support tools", "type": "invalid_request_error"}})
        base = {"id": "c1", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        if tools:
            fn = tools[0]["function"]
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": fn["name"], "arguments": json.dumps(_answer_for(fn.get("parameters")),
                                                                         ensure_ascii=False)}}]}
            finish = "tool_calls"
        else:
            text = json.dumps(body["messages"], ensure_ascii=False)
            if "number" in text and "status" in text:
                content = json.dumps({"status": "ok", "number": 42})
            elif "kind" in text:
                content = json.dumps(_answer_for({"properties": {"kind": {}}}), ensure_ascii=False)
            else:
                content = "连接正常"
            msg, finish = {"role": "assistant", "content": content}, "stop"
        return {**base, "choices": [{"index": 0, "message": msg, "finish_reason": finish}]}

    return app, seen


@pytest.fixture
def provider_server(monkeypatch):
    servers = []

    def start(mode: str):
        app, seen = make_provider(mode)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        servers.append(server)
        return f"http://127.0.0.1:{port}/v1", seen

    for k in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(k, "127.0.0.1,localhost")
    yield start
    for s in servers:
        s.should_exit = True


async def _setup_model(client, h, base_url: str, provider_type: str = "openai_compatible") -> str:
    p = (await client.post("/api/v1/admin/llm/providers", headers=h, json={
        "provider_name": "DeepSeek", "provider_type": provider_type, "base_url": base_url,
        "api_key": "sk-test-123456"})).json()
    m = (await client.post("/api/v1/admin/llm/models", headers=h, json={
        "provider_id": p["provider_id"], "model_name": "deepseek-flash"})).json()
    r = await client.put("/api/v1/admin/llm/agent-bindings/default", headers=h,
                         json={"model_profile_id": m["model_profile_id"]})
    assert r.status_code == 200
    return m["model_profile_id"]


async def test_thinking_model_rejecting_forced_tool_choice_is_adapted(client, env, provider_server):
    base_url, seen = provider_server("thinking")
    h = await register(client)
    mid = await _setup_model(client, h, base_url)
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "你好"})
    await run_worker()
    msg = [m for m in (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()["items"]
           if m["role"] == "assistant"][-1]
    assert msg["message_status"] == "final", msg
    assert parts_of(msg, "text")[0]["text"] == "你好，我是测试模型。"
    assert seen["tool_choice"][:2] == ["required", "auto"]  # 首次被拒 → 自动改为 auto 重试成功
    models = (await client.get("/api/v1/admin/llm/models", headers=h)).json()
    m = next(x for x in models if x["model_profile_id"] == mid)
    assert m["supports_forced_tool_choice"] is False and m["supports_tools"] is True  # 能力已记住
    # 再次对话直接使用 auto，不再被拒
    n = len(seen["tool_choice"])
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "你好"})
    await run_worker()
    assert seen["tool_choice"][n:] == ["auto"]


async def test_deepseek_provider_type_avoids_forced_tool_choice_upfront(client, env, provider_server):
    """供应方类型选 deepseek 时使用专用适配器：思考模型直接用 auto，不会先被拒一次。"""
    base_url, seen = provider_server("thinking")
    h = await register(client)
    mid = await _setup_model(client, h, base_url, provider_type="deepseek")
    r = (await client.post(f"/api/v1/admin/llm/models/{mid}/test", headers=h)).json()
    assert r["ok"] is True and r["adaptations"] == [], r
    assert "required" not in seen["tool_choice"]


async def test_admin_test_detects_and_adapts(client, env, provider_server):
    base_url, _ = provider_server("thinking")
    h = await register(client)
    mid = await _setup_model(client, h, base_url)
    r = (await client.post(f"/api/v1/admin/llm/models/{mid}/test", headers=h)).json()
    assert r["ok"] is True and r["structured_ok"] is True
    assert r["adaptations"] and "强制工具调用" in r["adaptations"][0]


async def test_model_without_tools_falls_back_to_prompted_json(client, env, provider_server):
    base_url, seen = provider_server("no_tools")
    h = await register(client)
    mid = await _setup_model(client, h, base_url)
    r = (await client.post(f"/api/v1/admin/llm/models/{mid}/test", headers=h)).json()
    assert r["ok"] is True, r
    m = next(x for x in (await client.get("/api/v1/admin/llm/models", headers=h)).json()
             if x["model_profile_id"] == mid)
    assert m["supports_tools"] is False  # 降级为提示词约束 JSON


def test_classify_ignores_unrelated_errors():
    from cloudsearch.llm.adapt import classify

    class E(Exception):
        def __init__(self, status, msg):
            super().__init__(msg)
            self.status_code, self.model_name, self.body = status, "m", {"message": msg}

    assert classify(E(400, "Thinking mode does not support this tool_choice")) == {"m": "no_forced_tool_choice"}
    assert classify(E(400, "tools are not supported for this model")) == {"m": "no_tools"}
    assert classify(E(401, "Thinking mode does not support this tool_choice")) == {}
    assert classify(E(400, "max_tokens is too large")) == {}
    assert classify(ExceptionGroup("g", [E(400, "tool_choice required unsupported")])) == {"m": "no_forced_tool_choice"}


async def test_auto_migrate_legacy_database(tmp_path, monkeypatch):
    """早期版本直接建表（无 alembic_version、缺新列）的库：自动识别、标记并升级。"""
    import sqlalchemy as sa

    from cloudsearch.core import config
    from cloudsearch.db import base
    from cloudsearch.db.migrate import auto_migrate

    db = tmp_path / "legacy.db"
    monkeypatch.setenv("CS_CONFIG_FILE", str(tmp_path / "none.yaml"))
    monkeypatch.setenv("CS_DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    config.get_settings.cache_clear()
    await base.dispose_engine()
    await base.create_all()
    async with base.get_engine().begin() as conn:  # 模拟早期结构：删掉后续版本新增的列
        await conn.execute(sa.text("ALTER TABLE src_opr_llm_model_f DROP COLUMN supports_forced_tool_choice"))
        for col in ("handoff_state", "handoff_reason", "handoff_deadline", "handoff_user_id", "live_endpoint"):
            await conn.execute(sa.text(f"ALTER TABLE src_opr_browser_session_f DROP COLUMN {col}"))
        await conn.execute(sa.text("DROP TABLE src_opr_system_setting_f"))
        await conn.execute(sa.text("DROP TABLE src_opr_file_f"))
    await auto_migrate()
    await auto_migrate()  # 幂等
    async with base.get_engine().connect() as conn:
        cols = await conn.run_sync(lambda c: {x["name"] for x in sa.inspect(c).get_columns("src_opr_llm_model_f")})
        ver = (await conn.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar()
    assert "supports_forced_tool_choice" in cols and ver == "d5e8f1a2b3c4"
    await base.dispose_engine()
    # 全新空库：从头迁移
    monkeypatch.setenv("CS_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'new.db').as_posix()}")
    config.get_settings.cache_clear()
    await auto_migrate()
    async with base.get_engine().connect() as conn:
        assert await conn.run_sync(lambda c: sa.inspect(c).has_table("src_opr_task_f"))
    await base.dispose_engine()
    config.get_settings.cache_clear()
