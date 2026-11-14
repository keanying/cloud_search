"""config.yaml 加载与 llm 分区同步。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _settings():
    from cloudsearch.core import config

    config.get_settings.cache_clear()
    return config.Settings()


def test_example_config_is_valid(tmp_path, monkeypatch):
    shutil.copy(ROOT / "config.example.yaml", tmp_path / "config.yaml")
    monkeypatch.setenv("CS_CONFIG_FILE", str(tmp_path / "config.yaml"))
    s = _settings()
    assert s.database_url.startswith("sqlite+aiosqlite:///") and s.database_url.endswith("backend/data/cloudsearch.db")
    assert s.server_port == 8000 and s.embedded_worker is True and s.search_engines == ["duckduckgo", "google", "bing", "baidu", "sogou"]


def test_mysql_section_and_env_override(tmp_path, monkeypatch):
    (tmp_path / "c.yaml").write_text("""
database:
  type: mysql
  mysql: {host: db.local, port: 3307, user: cs, password: "p@ss:w/rd", name: cloudsearch_app}
worker: {embedded: false, max_tasks: 5}
browser: {headless: false, proxy: }
storage: {dir: var/storage}
""", encoding="utf-8")
    monkeypatch.setenv("CS_CONFIG_FILE", str(tmp_path / "c.yaml"))
    monkeypatch.setenv("CS_WORKER_MAX_TASKS", "9")  # 环境变量优先
    s = _settings()
    assert s.database_url == "mysql+asyncmy://cs:p%40ss%3Aw%2Frd@db.local:3307/cloudsearch_app?charset=utf8mb4"
    assert s.embedded_worker is False and s.worker_max_tasks == 9 and s.browser_headless is False
    assert s.storage_dir == ROOT / "var" / "storage"


def test_unknown_key_is_rejected(tmp_path, monkeypatch):
    from cloudsearch.core.config import ConfigError

    (tmp_path / "c.yaml").write_text("browser:\n  headles: true\n", encoding="utf-8")
    monkeypatch.setenv("CS_CONFIG_FILE", str(tmp_path / "c.yaml"))
    with pytest.raises(ConfigError, match="browser.headles"):
        _settings()


async def test_llm_section_synced_to_db(env, tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("""
llm:
  providers:
    - name: DeepSeek
      type: deepseek
      base_url: https://api.deepseek.com/
      api_key: sk-abcdefghijklmnop
      models:
        - {name: deepseek-chat, input_price: 2, output_price: 8}
        - {name: deepseek-reasoner, supports_tools: false}
  bindings:
    default: {model: DeepSeek/deepseek-chat}
    extractor: {model: DeepSeek/deepseek-chat, fallbacks: [DeepSeek/deepseek-reasoner], temperature: 0}
""", encoding="utf-8")
    from cloudsearch.app import sync_config_to_db
    from cloudsearch.db.base import session_scope
    from cloudsearch.llm.registry import resolve_model

    await sync_config_to_db()
    await sync_config_to_db()  # 幂等
    async with session_scope() as s:
        rm = await resolve_model(s, "extractor")
        rd = await resolve_model(s, "search_planner")  # 未绑定 → default
    assert rm.pricing["deepseek-chat"].input_price_minor_amt == 200 and rm.temperature == 0
    assert rm.model.models[1].profile["default_structured_output_mode"] == "prompted"
    assert rd.primary_profile_id == rm.primary_profile_id
    from sqlalchemy import func, select

    from cloudsearch.db.models import LlmModel, LlmProvider

    async with session_scope() as s:
        assert (await s.execute(select(func.count()).select_from(LlmProvider))).scalar_one() == 1
        assert (await s.execute(select(func.count()).select_from(LlmModel))).scalar_one() == 2
    # 管理后台修改后重启：config.yaml 的 llm 分区未变 → 不覆盖后台修改；分区变化后才重新同步
    from cloudsearch.db.models import AgentModelBinding

    async with session_scope() as s:
        await s.delete(await s.get(AgentModelBinding, "extractor"))  # 后台“改用默认模型”
    await sync_config_to_db()
    async with session_scope() as s:
        assert await s.get(AgentModelBinding, "extractor") is None
    cfg = (tmp_path / "config.yaml").read_text(encoding="utf-8").replace("temperature: 0}", "temperature: 0.2}")
    (tmp_path / "config.yaml").write_text(cfg, encoding="utf-8")
    await sync_config_to_db()
    async with session_scope() as s:
        assert (await s.get(AgentModelBinding, "extractor")).temperature == 0.2


async def test_delete_agent_binding_falls_back_to_default(client, env):
    from conftest import register

    h = await register(client)
    p = (await client.post("/api/v1/admin/llm/providers", headers=h, json={
        "provider_name": "DeepSeek", "provider_type": "deepseek", "base_url": "https://api.deepseek.com/",
        "api_key": "sk-abcdefghijklmnop"})).json()
    m = (await client.post("/api/v1/admin/llm/models", headers=h, json={
        "provider_id": p["provider_id"], "model_name": "deepseek-chat"})).json()
    await client.put("/api/v1/admin/llm/agent-bindings/extractor", headers=h, json={"model_profile_id": m["model_profile_id"]})
    assert (await client.delete("/api/v1/admin/llm/agent-bindings/extractor", headers=h)).status_code == 204
    b = next(x for x in (await client.get("/api/v1/admin/llm/agent-bindings", headers=h)).json()
             if x["agent_role"] == "extractor")
    assert b["model_profile_id"] is None
    assert (await client.delete("/api/v1/admin/llm/agent-bindings/default", headers=h)).status_code == 400
