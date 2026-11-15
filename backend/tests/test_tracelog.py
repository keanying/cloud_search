"""执行日志：任务全过程可下载排查；人机验证判定给出具体命中规则并保存证据。"""

from __future__ import annotations

import uuid

from conftest import quick_task_output, register, run_worker


async def test_task_trace_download(client, fake_llm, fake_browser):
    h = await register(client)
    fake_llm.compiler_outputs.append(quick_task_output())
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "故宫什么时候开放？"})
    await run_worker()
    tid = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]["task_id"]
    r = await client.get(f"/api/v1/tasks/{tid}/trace", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    log = r.text
    assert "云搜浏览器 · 任务执行日志" in log and "配置摘要" in log
    for needle in ("[run]  开始执行", "[step]  plan 开始", "[step]  plan 完成", "[llm]  search_planner",
                   "[read]  读取成功", "[run]  结束：completed"):
        assert needle in log, needle
    assert "api_key" not in log and "sk-" not in log
    other = await register(client, "bob")
    assert (await client.get(f"/api/v1/tasks/{tid}/trace", headers=other)).status_code == 404


async def test_challenge_reason_explains_and_ignores_hidden_widgets(env, tmp_path):
    """真实浏览器：隐藏的 captcha 容器不算验证；可见的验证组件/关键词给出命中规则并保存截图。"""
    import pytest

    from cloudsearch.browser.pool import CloudBrowserSession, get_pool
    from cloudsearch.core.tracelog import current_task, trace_path
    from cloudsearch.search.engines import challenge_reason, page_is_challenge

    pool = get_pool()
    try:
        browser = await pool._ensure()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no browser: {e}")
    ctx = await browser.new_context()
    page = await ctx.new_page()
    sess = CloudBrowserSession("t", ctx, page)
    try:
        await page.set_content("<p>正常页面" + "内容" * 50 + "</p><div class='login-captcha' style='display:none'>x</div>")
        assert await challenge_reason(sess) is None  # 隐藏的 captcha 容器不再误判
        await page.set_content("<div class='g-recaptcha' style='width:300px;height:80px'></div>")
        assert "可见的验证组件" in (await challenge_reason(sess)) and ".g-recaptcha" in await challenge_reason(sess)
        await page.set_content("<h1>请完成安全验证</h1>")
        token = current_task.set("tsk_trace_test")
        try:
            assert await page_is_challenge(sess, where="测试")
        finally:
            current_task.reset(token)
        line = trace_path("tsk_trace_test").read_text(encoding="utf-8")
        assert "[challenge]  测试 判定为人机验证/拦截：页面文字含“安全验证”" in line and "logs/challenges/" in line
        assert sess.challenge_reason.startswith("页面文字含")
    finally:
        await ctx.close()
        await pool.close()


async def test_debug_bundle_records_agents_search_and_reads(client, fake_llm, fake_browser):
    """详细调试记录：开启后记录智能体完整输入输出、读取正文；管理员可按任务或全系统下载 ZIP；普通用户不可下载。"""
    import io
    import json
    import zipfile

    h = await register(client)  # 第一个用户是管理员
    r = await client.put("/api/v1/admin/settings", headers=h, json={"values": {"logs_debug": True}})
    assert r.status_code == 200
    from cloudsearch.core import runtime

    await runtime.refresh(force=True)
    fake_llm.compiler_outputs.append(quick_task_output())
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "故宫什么时候开放？"})
    await run_worker()
    tid = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]["task_id"]

    st = (await client.get("/api/v1/admin/debug/status", headers=h)).json()
    assert st["enabled"] is True and st["files"]

    r = await client.get(f"/api/v1/admin/debug/bundle?task_id={tid}", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    base = next(n for n in names if n.startswith(f"tasks/{tid}_")).split("/")[1]
    for f in ("trace.log", "task.json", "steps.json", "agent_runs.json", "search_candidates.json", "sources.json",
              "evidence.json", "messages.json", "debug.jsonl"):
        assert f"tasks/{base}/{f}" in names, f
    assert any(n.startswith(f"tasks/{base}/sources_text/") for n in names)
    rows = [json.loads(x) for x in z.read(f"tasks/{base}/debug.jsonl").decode().splitlines()]
    kinds = {r["kind"] for r in rows}
    assert {"llm", "read"} <= kinds
    llm = next(r for r in rows if r["kind"] == "llm" and r.get("agent_role") == "requirement_compiler")
    assert llm["prompt"] and llm["output"] and llm["conversation_id"] == cid  # 理解需求（任务创建前）也归入
    read = next(r for r in rows if r["kind"] == "read")
    assert read["text_excerpt"] and read["method"] in ("http", "browser")
    steps = json.loads(z.read(f"tasks/{base}/steps.json"))
    assert any(s["output_json"] for s in steps)
    assert "api_key" not in z.read("system/config.json").decode()

    r = await client.get("/api/v1/admin/debug/bundle?hours=2&include_text=false", headers=h)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "README.md" in names and "system/errors.json" in names and any(n.startswith("system/debug/") for n in names)
    assert not any("sources_text/" in n for n in names)

    other = await register(client, "bob")
    assert (await client.get("/api/v1/admin/debug/bundle", headers=other)).status_code == 403
