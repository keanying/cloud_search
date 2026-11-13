"""端到端：对话 → 需求编译 → 任务 → 八角色流水线 → 成果；以及幂等、停止、暂停恢复、越权。"""

from __future__ import annotations

import asyncio
import uuid

from conftest import parts_of, quick_task_output, register, run_worker


async def _conv(client, h) -> str:
    r = await client.post("/api/v1/conversations", json={}, headers=h)
    assert r.status_code == 201
    return r.json()["conversation_id"]


async def _send(client, h, cid, text, mode="auto", cmid=None):
    return await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                             json={"client_message_id": cmid or str(uuid.uuid4()), "text": text,
                                   "mode_selection": mode})


async def _assistant(client, h, cid) -> dict:
    r = await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)
    return [m for m in r.json()["items"] if m["role"] == "assistant"][-1]


async def test_chat_reply_does_not_create_task(client, fake_llm, fake_browser):
    h = await register(client)
    cid = await _conv(client, h)
    r = await _send(client, h, cid, "你好")
    assert r.status_code == 202
    await run_worker()
    msg = await _assistant(client, h, cid)
    assert msg["message_status"] == "final"
    assert parts_of(msg, "text")[0]["text"].startswith("你好")
    assert (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json() == []
    conv = (await client.get(f"/api/v1/conversations/{cid}", headers=h)).json()
    assert conv["title"] == "问候"
    assert fake_browser.reads == []  # 普通对话不启动浏览器


async def test_quick_search_end_to_end(client, fake_llm, fake_browser):
    h = await register(client)
    cid = await _conv(client, h)
    fake_llm.compiler_outputs.append(quick_task_output())
    await _send(client, h, cid, "故宫什么时候开放？")
    await run_worker()
    tasks = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()
    assert len(tasks) == 1 and tasks[0]["task_status"] == "completed", tasks
    tid = tasks[0]["task_id"]
    msg = await _assistant(client, h, cid)
    answer = next(p for p in msg["parts"] if p["part_id"].startswith("answer-"))
    assert "[1]" in answer["text"] and "[9]" not in answer["text"]  # 不存在的引用被程序删除
    assert [c["n"] for c in answer["citations"]] == [1]
    progress = parts_of(msg, "progress")[0]
    assert progress["task_status"] == "completed"
    assert all(s["status"] in ("done", "skipped") for s in progress["stages"])
    assert progress["counters"]["sources_read"] == 2
    assert parts_of(msg, "plan_summary")[0]["status"] == "auto_started"
    # 来源：序号与引用一致；证据为原文子串且已机器核验
    src = (await client.get(f"/api/v1/tasks/{tid}/sources", headers=h)).json()
    assert sorted(s["n"] for s in src["sources"]) == [1, 2]
    ev = src["sources"][0]["evidence"][0]
    assert ev["verification_status"] == "machine_checked"
    assert ev["quote_text"] in "故宫博物院每周一闭馆，法定节假日除外。名称：故宫博物院，票价：60元。更多介绍内容。" * 3 or \
        ev["quote_text"] in "国家博物馆周二至周日开放，周一闭馆。名称：国家博物馆，票价：0元。其他信息。" * 3
    assert len(src["candidates"]) == 2
    # 阅览：列出真实会话（已结束）；没有画面时快照 404
    sessions = (await client.get(f"/api/v1/tasks/{tid}/browser-sessions", headers=h)).json()
    assert sessions and sessions[0]["session_status"] == "closed"
    meta = (await client.get(f"/api/v1/browser-sessions/{sessions[0]['browser_session_id']}/viewer-meta",
                             headers=h)).json()
    assert meta["preview_mode"] == "snapshot" and meta["connected"] is False and meta["stale"] is True
    snap = await client.get(f"/api/v1/browser-sessions/{sessions[0]['browser_session_id']}/viewer-snapshot",
                            headers=h)
    assert snap.status_code == 404
    # 每个角色各司其职：普通问答路线不调用 analyst/coordinator
    assert fake_llm.calls.get("search_planner") == 1 and fake_llm.calls.get("report_writer") == 1
    assert fake_llm.calls.get("extractor") == 2 and fake_llm.calls.get("verifier") == 1
    assert "analyst" not in fake_llm.calls and "coordinator" not in fake_llm.calls


async def test_send_is_idempotent(client, fake_llm, fake_browser):
    h = await register(client)
    cid = await _conv(client, h)
    cmid = str(uuid.uuid4())
    r1 = await _send(client, h, cid, "你好", cmid=cmid)
    r2 = await _send(client, h, cid, "你好", cmid=cmid)
    assert r1.status_code == 202 and r2.status_code == 200 and r2.json()["deduplicated"] is True
    assert r1.json()["user_message"]["message_id"] == r2.json()["user_message"]["message_id"]
    r3 = await _send(client, h, cid, "别的内容", cmid=cmid)
    assert r3.status_code == 409
    items = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()["items"]
    assert len(items) == 2


DATASET = {"entity": "一个博物馆", "fields": [
    {"key": "name", "label": "名称", "type": "string", "required": True},
    {"key": "price", "label": "票价", "type": "number", "unit": "元"},
    {"key": "note", "label": "备注", "type": "string"}], "max_records": 10, "analysis_request": "统计数量"}


async def test_dataset_requires_confirmation_and_exports(client, fake_llm, fake_browser):
    h = await register(client)
    cid = await _conv(client, h)
    fake_llm.compiler_outputs.append(quick_task_output(mode="dataset", dataset=DATASET))
    await _send(client, h, cid, "采集博物馆票价，整理CSV")
    await run_worker()
    task = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]
    assert task["task_status"] == "draft" and task["status_reason"] == "approval"
    assert fake_browser.reads == []  # 未确认不执行
    r = await client.post(f"/api/v1/tasks/{task['task_id']}/confirm", json={"plan_hash": "wrong"}, headers=h)
    assert r.status_code == 412
    r = await client.post(f"/api/v1/tasks/{task['task_id']}/confirm", json={"plan_hash": task["plan_hash"]}, headers=h)
    assert r.status_code == 200 and r.json()["task_status"] == "queued"
    await run_worker()
    task = (await client.get(f"/api/v1/tasks/{task['task_id']}", headers=h)).json()
    assert task["task_status"] == "completed", task
    msg = await _assistant(client, h, cid)
    arts = parts_of(msg, "artifact")
    names = sorted(a["display_name"].rsplit(".", 1)[1] for a in arts)
    assert names == ["csv", "md", "xlsx"]  # 数据文件 + 分析
    csv_art = next(a for a in arts if a["display_name"].endswith(".csv"))
    assert csv_art["record_qty"] == 2
    prev = (await client.get(f"/api/v1/artifacts/{csv_art['artifact_id']}/preview", headers=h)).json()
    assert prev["kind"] == "table" and prev["total_rows"] == 2
    assert prev["columns"][:3] == ["名称", "票价", "备注"]
    row = next(r for r in prev["rows"] if r[0] == "故宫博物院")
    assert row[1] == "60"
    assert row[2] == ""  # 备注的摘录不在原文中 → 不采用，置空并说明原因
    assert "摘录未能校验" in row[4]
    dl = await client.get(f"/api/v1/artifacts/{csv_art['artifact_id']}/download", headers=h)
    assert dl.status_code == 200 and dl.headers["x-content-sha256"] == csv_art["content_hash"]
    mine = (await client.get("/api/v1/artifacts", headers=h)).json()
    assert len(mine) == 3 and all(a["conversation_id"] == cid for a in mine)


async def test_stop_current_turn_quarantines_late_results(client, fake_llm, fake_browser):
    from cloudsearch.worker.main import Worker

    h = await register(client)
    cid = await _conv(client, h)
    fake_llm.compiler_outputs.append(quick_task_output())
    fake_browser.read_gate = asyncio.Event()
    await _send(client, h, cid, "故宫什么时候开放？")
    w = Worker("w-test")
    await w.tick()
    await asyncio.gather(*w.turns)
    await w.tick()  # 领取运行
    for _ in range(100):
        if fake_browser.reads:
            break
        await asyncio.sleep(0.05)
    assert fake_browser.reads, "读取应已开始"
    r = await client.post(f"/api/v1/conversations/{cid}/stop-turn", json={}, headers=h)
    assert r.json()["results"][0]["outcome"] == "accepted"
    assert r.json()["results"][0]["task_status"] == "stopping"
    fake_browser.read_gate.set()  # 迟到的读取结果
    await w.drain()
    task = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]
    assert task["task_status"] == "stopped"
    src = (await client.get(f"/api/v1/tasks/{task['task_id']}/sources", headers=h)).json()
    assert src["sources"] == []  # 停止后的迟到结果没有进入正式来源
    assert "report_writer" not in fake_llm.calls  # 停止后不再发起有价请求
    msg = await _assistant(client, h, cid)
    assert any("已按你的要求停止" in p.get("text", "") for p in parts_of(msg, "text"))
    from cloudsearch.db.base import session_scope
    from cloudsearch.db.models import TaskStep
    from sqlalchemy import select

    async with session_scope() as s:
        steps = (await s.execute(select(TaskStep).where(TaskStep.node_id.like("read:%")))).scalars().all()
    assert steps and all(st.step_status == "cancelled" for st in steps), \
        [(st.step_status, st.error_code) for st in steps]


async def test_pause_then_resume_reuses_completed_steps(client, fake_llm, fake_browser):
    from cloudsearch.worker.main import Worker

    h = await register(client)
    cid = await _conv(client, h)
    fake_llm.compiler_outputs.append(quick_task_output())
    fake_llm.gate = asyncio.Event()  # 卡在写作前
    await _send(client, h, cid, "故宫什么时候开放？")
    w = Worker("w-test")
    await w.tick()
    await asyncio.gather(*w.turns)
    await w.tick()
    tid = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]["task_id"]
    for _ in range(200):
        if fake_llm.calls.get("report_writer"):
            break
        await asyncio.sleep(0.05)
    r = await client.post(f"/api/v1/tasks/{tid}/pause", headers=h)
    assert r.json()["task_status"] == "pausing"
    fake_llm.gate.set()
    await w.drain()
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=h)).json()["task_status"] == "paused"
    planner_calls = fake_llm.calls["search_planner"]
    reads = len(fake_browser.reads)
    r = await client.post(f"/api/v1/tasks/{tid}/resume", headers=h)
    assert r.json()["task_status"] == "queued"
    await run_worker()
    task = (await client.get(f"/api/v1/tasks/{tid}", headers=h)).json()
    assert task["task_status"] == "completed"
    assert fake_llm.calls["search_planner"] == planner_calls  # 已完成节点复用，不重复调用
    assert len(fake_browser.reads) == reads  # 不重新读取


async def test_other_user_cannot_access(client, fake_llm, fake_browser):
    ha = await register(client, "alice")
    hb = await register(client, "bob")
    cid = await _conv(client, ha)
    fake_llm.compiler_outputs.append(quick_task_output())
    await _send(client, ha, cid, "故宫什么时候开放？")
    await run_worker()
    tid = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=ha)).json()[0]["task_id"]
    assert (await client.get(f"/api/v1/conversations/{cid}", headers=hb)).status_code == 404
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=hb)).status_code == 404
    assert (await client.post(f"/api/v1/tasks/{tid}/stop", headers=hb)).status_code == 404
    assert (await client.get(f"/api/v1/tasks/{tid}/sources", headers=hb)).status_code == 404
    bs = (await client.get(f"/api/v1/tasks/{tid}/browser-sessions", headers=ha)).json()[0]
    assert (await client.get(f"/api/v1/browser-sessions/{bs['browser_session_id']}/viewer-meta",
                             headers=hb)).status_code == 404
    assert (await client.get("/api/v1/admin/llm/providers", headers=hb)).status_code == 403
    assert hb.user["is_admin"] is False and ha.user["is_admin"] is True


async def test_llm_not_configured_reports_clearly(client, env, fake_browser):
    h = await register(client)
    cid = await _conv(client, h)
    await _send(client, h, cid, "你好")
    await run_worker()
    msg = await _assistant(client, h, cid)
    assert msg["message_status"] == "error"
    assert parts_of(msg, "error")[0]["code"] == "llm_not_configured"


async def test_admin_llm_config_and_binding(client, env):
    h = await register(client)
    r = await client.post("/api/v1/admin/llm/providers", headers=h, json={
        "provider_name": "DeepSeek", "provider_type": "deepseek", "base_url": "https://api.deepseek.com/",
        "api_key": "sk-abcdefghijklmnop"})
    assert r.status_code == 201
    p = r.json()
    assert p["has_api_key"] and p["api_key_mask"] == "sk-****mnop" and "api_key" not in p
    m = (await client.post("/api/v1/admin/llm/models", headers=h, json={
        "provider_id": p["provider_id"], "model_name": "deepseek-chat", "supports_tools": True,
        "input_price_minor_amt": 200, "output_price_minor_amt": 800})).json()
    m2 = (await client.post("/api/v1/admin/llm/models", headers=h, json={
        "provider_id": p["provider_id"], "model_name": "deepseek-reasoner", "supports_tools": False,
        "supports_json_object": True})).json()
    r = await client.put("/api/v1/admin/llm/agent-bindings/extractor", headers=h, json={
        "model_profile_id": m["model_profile_id"], "fallback_profile_ids": [m2["model_profile_id"]]})
    assert r.status_code == 200
    bindings = (await client.get("/api/v1/admin/llm/agent-bindings", headers=h)).json()
    assert len(bindings) == 9 and next(b for b in bindings if b["agent_role"] == "extractor")["fallback_profile_ids"]
    # 解析：主模型 + 备用链；无工具能力的模型使用 prompted 输出
    from cloudsearch.db.base import session_scope
    from cloudsearch.llm.registry import resolve_model
    from pydantic_ai.models.fallback import FallbackModel

    async with session_scope() as s:
        rm = await resolve_model(s, "extractor")
    assert isinstance(rm.model, FallbackModel)
    assert rm.pricing["deepseek-chat"].cost(1_000_000, 1_000_000) == 1000
    assert rm.pricing["deepseek-reasoner"].cost(10, 10) is None  # 单价未知不记 0
    assert rm.model.models[1].profile["default_structured_output_mode"] == "prompted"
    assert (await client.delete(f"/api/v1/admin/llm/models/{m['model_profile_id']}", headers=h)).status_code == 409
