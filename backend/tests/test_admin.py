"""管理后台：概览、列表、用户管理、运行参数在线修改（覆盖 config.yaml、恢复默认、对新任务生效）。"""

from __future__ import annotations

import uuid

from conftest import quick_task_output, register, run_worker


async def _one_task(client, h, fake_llm):
    fake_llm.compiler_outputs.append(quick_task_output())
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "故宫什么时候开放？"})
    await run_worker()
    return cid


async def test_overview_and_lists(client, fake_llm, fake_browser):
    admin = await register(client, "admin")
    bob = await register(client, "bob")
    cid = await _one_task(client, admin, fake_llm)
    assert (await client.get("/api/v1/admin/overview", headers=bob)).status_code == 403

    ov = (await client.get("/api/v1/admin/overview?days=7", headers=admin)).json()
    assert ov["totals"]["users"] == 2 and ov["totals"]["tasks"] == 1 and ov["totals"]["sources_read"] == 2
    assert ov["task_status"] == {"completed": 1}
    assert len(ov["tasks_by_day"]) == 7 and ov["tasks_by_day"][-1]["completed"] == 1
    roles = {r["role"]: r for r in ov["llm_by_role"]}
    assert roles["extractor"]["requests"] == 2 and roles["extractor"]["label"] == "信息抽取"
    assert ov["llm"]["requests"] >= 4
    assert {e["name"] for e in ov["engines"]} >= {"duckduckgo", "bing", "wikipedia_zh"}
    assert ov["engines"][0]["kind"] == "general" and ov["engines"][0]["enabled"]

    runs = (await client.get("/api/v1/admin/agent-runs?size=3&role=extractor", headers=admin)).json()
    assert runs["total"] == 2 and len(runs["items"]) == 2 and runs["items"][0]["role_label"] == "信息抽取"
    assert (await client.get("/api/v1/admin/agent-runs?status=failed", headers=admin)).json()["total"] == 0

    tasks = (await client.get("/api/v1/admin/tasks?q=故宫", headers=admin)).json()
    assert tasks["total"] == 1 and tasks["items"][0]["username"] == "admin"
    assert tasks["items"][0]["conversation_id"] == cid
    assert (await client.get("/api/v1/admin/tasks?status=active", headers=admin)).json()["total"] == 0

    tid = tasks["items"][0]["task_id"]
    d = (await client.get(f"/api/v1/admin/tasks/{tid}", headers=admin)).json()
    assert d["task"]["task_id"] == tid and d["spec"]["requirement_text"]
    assert d["runs"] and d["runs"][0]["run_status"] == "completed"
    assert any(st["agent_role"] == "extractor" and st["role_label"] == "信息抽取" for st in d["steps"])
    assert d["sources"]["by_status"] == {"captured": 2} and d["sources"]["items"][0]["credibility_label"]
    assert d["llm"]["requests"] >= 4 and d["llm"]["failed"] == 0
    assert (await client.get("/api/v1/admin/tasks/nope", headers=admin)).status_code == 404

    users = (await client.get("/api/v1/admin/users", headers=admin)).json()
    assert users["total"] == 2
    me = next(u for u in users["items"] if u["username"] == "admin")
    assert me["is_admin"] and me["task_qty"] == 1 and me["conversation_qty"] == 1
    ud = (await client.get(f"/api/v1/admin/users/{me['user_id']}", headers=admin)).json()
    assert ud["llm_requests"] >= 4 and ud["recent_tasks"][0]["task_id"] == tid


async def test_user_management_guards(client, env):
    admin = await register(client, "admin")
    bob = await register(client, "bob")
    r = await client.patch(f"/api/v1/admin/users/{admin.user['user_id']}", headers=admin, json={"is_admin": False})
    assert r.status_code == 400
    r = await client.patch(f"/api/v1/admin/users/{bob.user['user_id']}", headers=admin, json={"is_admin": True})
    assert r.json()["is_admin"] is True
    r = await client.patch(f"/api/v1/admin/users/{bob.user['user_id']}", headers=admin,
                           json={"user_status": "disabled"})
    assert r.json()["user_status"] == "disabled"
    assert (await client.get("/api/v1/conversations", headers=bob)).status_code == 401  # 停用后立即失效


async def test_runtime_settings_override_and_reset(client, fake_llm, fake_browser):
    from cloudsearch.core.config import get_settings

    admin = await register(client, "admin")
    cfg = (await client.get("/api/v1/admin/settings", headers=admin)).json()
    fields = {f["key"]: f for f in cfg["fields"]}
    assert fields["search_engines"]["type"] == "engine_order" and not fields["search_engines"]["overridden"]
    assert {"duckduckgo", "google"} <= {o["value"] for o in fields["search_engines"]["options"]}
    assert "wikipedia_zh" in fields["search_vertical_sources"]["value"]  # 未限制 = 全部
    assert any(g["group"] == "数据库" for g in cfg["static"])
    default_max = fields["task_max_sources"]["value"]

    bad = await client.put("/api/v1/admin/settings", headers=admin, json={"values": {"task_max_sources": 999}})
    assert bad.status_code == 422 and "1–40" in bad.json()["detail"]
    bad = await client.put("/api/v1/admin/settings", headers=admin, json={"values": {"search_engines": ["nope"]}})
    assert bad.status_code == 422

    r = await client.put("/api/v1/admin/settings", headers=admin, json={"values": {
        "task_max_sources": 1, "search_engines": ["bing", "duckduckgo"], "browser_takeover_enabled": False,
        "search_vertical_sources": ["arxiv"]}})
    fields = {f["key"]: f for f in r.json()["fields"]}
    assert fields["task_max_sources"]["overridden"] and fields["task_max_sources"]["value"] == 1
    assert fields["task_max_sources"]["default"] == default_max
    s = get_settings()
    assert s.search_engines == ["bing", "duckduckgo"] and s.browser_takeover_enabled is False
    assert s.search_vertical_sources == ["arxiv"]

    # 新任务按新上限执行：只读 1 个来源
    await _one_task(client, admin, fake_llm)
    assert len(fake_browser.reads) == 1

    r = await client.delete("/api/v1/admin/settings/task_max_sources", headers=admin)
    fields = {f["key"]: f for f in r.json()["fields"]}
    assert not fields["task_max_sources"]["overridden"] and get_settings().task_max_sources == default_max
    for k in ("search_engines", "browser_takeover_enabled", "search_vertical_sources"):
        await client.delete(f"/api/v1/admin/settings/{k}", headers=admin)
    assert get_settings().browser_takeover_enabled is True and get_settings().search_vertical_sources is None
