"""数据不出域：外部大模型被拒绝、云端解析被禁用、涉及文件的任务不联网；本地 Ollama 模型自动登记。"""

from __future__ import annotations

import uuid

import pytest

from conftest import quick_task_output, register, run_worker


def test_internal_host_rules(env, monkeypatch):
    from cloudsearch.core import privacy
    from cloudsearch.core.config import get_settings

    assert privacy.url_internal("http://127.0.0.1:11434/v1")
    assert privacy.url_internal("http://10.2.3.4:8000/v1") and privacy.url_internal("http://gpu01.lan:8000")
    assert not privacy.url_internal("http://198.18.0.5/v1")  # 代理 fake-ip 不算内网
    assert not privacy.url_internal("https://8.8.8.8/v1")
    monkeypatch.setattr(get_settings(), "privacy_allowed_hosts", ["llm.corp.example"])
    assert privacy.url_internal("https://gw.llm.corp.example/v1")


async def test_external_llm_refused_when_local_only(client, env, monkeypatch):
    from cloudsearch.core.config import get_settings
    from cloudsearch.db.base import session_scope
    from cloudsearch.llm.registry import LlmNotConfigured, resolve_model

    h = await register(client)
    p = (await client.post("/api/v1/admin/llm/providers", headers=h, json={
        "provider_name": "公网", "provider_type": "openai_compatible", "base_url": "https://8.8.8.8/v1",
        "api_key": "sk-abcdefghijklmnop"})).json()
    m = (await client.post("/api/v1/admin/llm/models", headers=h, json={
        "provider_id": p["provider_id"], "model_name": "x"})).json()
    monkeypatch.setattr(get_settings(), "privacy_data_local_only", True)
    async with session_scope() as s:
        with pytest.raises(LlmNotConfigured, match="数据不出域"):
            await resolve_model(s, "extractor")
    r = await client.post(f"/api/v1/admin/llm/models/{m['model_profile_id']}/test", headers=h)
    assert r.status_code == 409 and "数据不出域" in r.json()["detail"]


async def test_cloud_parsers_disabled(env, monkeypatch):
    from cloudsearch.core.config import get_settings
    from cloudsearch.files import parsers

    s = get_settings()
    monkeypatch.setattr(s, "mineru_cloud_token", "tok")
    assert "mineru_cloud" in parsers.candidates("pdf")
    monkeypatch.setattr(s, "privacy_data_local_only", True)
    assert parsers.candidates("pdf") == ["builtin"]
    with pytest.raises(parsers.ParseError, match="只在本机解析"):
        parsers.candidates("png")
    monkeypatch.setattr(s, "mineru_local", True)  # 本机托管 MinerU：自动使用 127.0.0.1:8002
    assert parsers.candidates("png") == ["mineru_api"] and parsers.api_url() == "http://127.0.0.1:8002"


async def test_file_task_stays_offline(client, fake_llm, fake_browser, monkeypatch):
    from cloudsearch.core.config import get_settings

    monkeypatch.setattr(get_settings(), "privacy_data_local_only", True)
    h = await register(client)
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    fid = (await client.post(f"/api/v1/conversations/{cid}/files", headers=h, files={
        "files": ("内部.txt", "内部数据：项目代号 A。".encode(), "text/plain")})).json()[0]["file_id"]
    out = quick_task_output()
    out["task_spec"]["scope"] = {"questions": ["项目代号？"], "file_ids": [fid], "use_web": True}  # 模型要求联网
    fake_llm.compiler_outputs.append(out)
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h, json={
        "client_message_id": str(uuid.uuid4()), "text": "项目代号是什么，顺便上网查查", "file_ids": [fid]})
    await run_worker()
    task = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]
    assert task["task_status"] == "completed", task
    assert fake_browser.queries == []  # 程序强制不联网


async def test_ollama_models_registered(env, monkeypatch):
    from cloudsearch.core.config import get_settings
    from cloudsearch.db.base import session_scope
    from cloudsearch.db.models import AgentModelBinding, LlmModel, LlmProvider
    from cloudsearch.llm.seed import sync_local_llm

    monkeypatch.setattr(get_settings(), "local_llm_ollama_models", ["qwen3:8b", "qwen3:32b"])
    async with session_scope() as s:
        await sync_local_llm(s)
    async with session_scope() as s:
        await sync_local_llm(s)  # 幂等
    async with session_scope() as s:
        from sqlalchemy import func, select

        p = (await s.execute(select(LlmProvider))).scalar_one()
        assert p.base_url == "http://127.0.0.1:11434/v1"
        assert (await s.execute(select(func.count()).select_from(LlmModel))).scalar_one() == 2
        b = await s.get(AgentModelBinding, "default")
        m = await s.get(LlmModel, b.model_profile_id)
        assert m.model_name == "qwen3:8b"


async def test_local_mineru_never_uses_cloud(env, monkeypatch):
    """mineru.local=true（大模型可用 DeepSeek 等公网厂商）：文件只在本机解析，误配云端 Token 也不会上传。"""
    from cloudsearch.core.config import get_settings
    from cloudsearch.files import parsers

    s = get_settings()
    monkeypatch.setattr(s, "mineru_local", True)
    monkeypatch.setattr(s, "mineru_cloud_token", "tok")
    assert parsers.candidates("pdf") == ["mineru_api", "builtin"]
    assert parsers.candidates("png") == ["mineru_api"]
    monkeypatch.setattr(s, "files_parser", "mineru_cloud")
    assert "mineru_cloud" not in parsers.candidates("pdf")
    assert not s.privacy_data_local_only  # 不影响大模型：公网厂商照常可用
