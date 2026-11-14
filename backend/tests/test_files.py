"""上传文件：内置解析、MinerU（自部署 4.x / 旧版、云端）协议、自动回退、分段、端到端文件问答。"""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest

from conftest import parts_of, register, run_worker


# ---------------------------------------------------------------- 内置解析
def _docx_bytes() -> bytes:
    from docx import Document

    d = Document()
    d.add_heading("年度经营报告", level=1)
    d.add_paragraph("2025 年营业收入 12.5 亿元，同比增长 18%。")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "指标", "数值"
    t.cell(1, 0).text, t.cell(1, 1).text = "毛利率", "42%"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_builtin_parsers():
    from openpyxl import Workbook

    from cloudsearch.files.parsers import ParseError, builtin_parse

    md = builtin_parse(_docx_bytes(), "docx").markdown
    assert "## 年度经营报告" in md and "12.5 亿元" in md and "| 毛利率 | 42% |" in md

    wb = Workbook()
    ws = wb.active
    ws.title = "门店"
    ws.append(["城市", "门店数"])
    ws.append(["上海", 12])
    buf = io.BytesIO()
    wb.save(buf)
    md = builtin_parse(buf.getvalue(), "xlsx").markdown
    assert "## 工作表：门店" in md and "| 上海 | 12 |" in md

    assert "| 北京 | 3 |" in builtin_parse("城市,数量\n北京,3\n".encode("gbk"), "csv").markdown

    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    with pytest.raises(ParseError, match="扫描件"):
        builtin_parse(buf.getvalue(), "pdf")
    with pytest.raises(ParseError, match="MinerU"):
        builtin_parse(b"\x89PNG....", "png")


def test_segments_split_long_documents():
    from cloudsearch.files.service import outline_of, segments

    md = "".join(f"## 第{i}章 标题{i}\n" + ("内容。" * 3000) + "\n" for i in range(1, 5))
    segs = segments(md, max_chars=10000)
    assert len(segs) >= 4 and segs[0][0].startswith("第 1 部分：第1章")
    assert "".join(t for _, t in segs) == md
    assert segments("短文", 100) == [("", "短文")]
    paged = "".join(f"〔第 {i} 页〕\n" + "字" * 6000 + "\n" for i in range(1, 5))
    assert segments(paged, 13000)[0][0] == "第 1–2 页"
    assert outline_of("# A\n## B\n正文") == ["A", "  B"]


# ---------------------------------------------------------------- MinerU 协议（模拟服务）
def _zip(md: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("report/full.md", md)
        z.writestr("report/images/a.png", b"png")
    return buf.getvalue()


def _mock_client(monkeypatch, handler):
    import httpx

    from cloudsearch.files import parsers

    def factory(timeout, **kw):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(parsers, "_client", factory)


async def test_mineru_api_v4_zip_and_polling(env, monkeypatch):
    from cloudsearch.core.config import get_settings
    from cloudsearch.files import parsers

    s = get_settings()
    monkeypatch.setattr(s, "mineru_api_url", "http://mineru.local:8003")
    calls = []

    def handler(req):
        import httpx

        calls.append((req.method, req.url.path))
        if req.url.path == "/v1/file_parse":
            body = req.content.decode("latin-1")
            assert 'name="tier"' in body and 'name="file"; filename="scan.pdf"' in body
            return httpx.Response(202, json={"request_id": "r1", "result_url": "/v1/file_parse/r1/result"})
        if len([c for c in calls if c[1].endswith("/result")]) < 2:
            return httpx.Response(409, json={"error": {"code": "result_not_ready", "message": "wait"}})
        return httpx.Response(200, content=_zip("# 扫描报告\n\n收入 3 亿元\n\n![图1](images/a.png)"))

    _mock_client(monkeypatch, handler)
    monkeypatch.setattr(parsers.asyncio, "sleep", lambda *_: _noop())
    res = await parsers.parse_bytes(b"%PDF-fake", "scan.pdf", "pdf")
    assert res.parser == "mineru_api" and "收入 3 亿元" in res.markdown and "〔图片：图1〕" in res.markdown
    assert res.image_qty == 1 and calls[0] == ("POST", "/v1/file_parse")


async def test_mineru_api_server_tasks_api(env, monkeypatch):
    """只启动 mineru-kit api-server（没有 file-parse-server）时走 Tasks API。"""
    import httpx

    from cloudsearch.core.config import get_settings
    from cloudsearch.files import parsers

    monkeypatch.setattr(get_settings(), "mineru_api_url", "http://127.0.0.1:8002")
    monkeypatch.setattr(parsers.asyncio, "sleep", lambda *_: _noop())
    seen = {"polls": 0}

    def handler(req):
        import json as _j

        p = req.url.path
        if p == "/v1/file_parse":
            return httpx.Response(404)
        if p == "/v1/tasks" and req.method == "POST":
            body = _j.loads(req.content)
            assert body["files"][0] == {"file_name": "合同.pdf", "bytes": 4} and body["page_range"] == "all"
            return httpx.Response(202, json={"task_id": "t1", "status": "waiting-file", "files": [
                {"file_id": "f1", "file_name": "合同.pdf", "status": "waiting-file",
                 "upload": {"url": "/v1/tasks/t1/uploads/f1", "headers": {"X-Upload": "1"}}}]})
        if p == "/v1/tasks/t1/uploads/f1":
            assert req.method == "PUT" and req.content == b"%PDF" and req.headers["x-upload"] == "1"
            seen["uploaded"] = True
            return httpx.Response(204)
        if p == "/v1/tasks/t1":
            seen["polls"] += 1
            st = "running" if seen["polls"] < 2 else "completed"
            return httpx.Response(200, json={"task_id": "t1", "status": st, "files": [
                {"file_id": "f1", "status": st, "result_url": "/v1/files/f1/content" if st == "completed" else None}]})
        if p == "/v1/files/f1/content":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("markdown.md", "# 合同\n甲方：某公司")
                z.writestr("structured_content.json", "{}")
            return httpx.Response(200, content=buf.getvalue())
        return httpx.Response(500)

    _mock_client(monkeypatch, handler)
    res = await parsers.parse_bytes(b"%PDF", "合同.pdf", "pdf")
    assert res.parser == "mineru_api" and "甲方：某公司" in res.markdown and seen["uploaded"]


async def _noop():
    return None


async def test_mineru_legacy_api_and_fallback(env, monkeypatch):
    import httpx

    from cloudsearch.core.config import get_settings
    from cloudsearch.files import parsers

    s = get_settings()
    monkeypatch.setattr(s, "mineru_api_url", "http://mineru.local:8000")

    def legacy(req):
        if req.url.path == "/v1/file_parse":
            return httpx.Response(404)
        return httpx.Response(200, json={"results": {"doc": {"md_content": "# 旧版\n内容"}}})

    _mock_client(monkeypatch, legacy)
    res = await parsers.parse_bytes(b"x", "a.pptx", "pptx")
    assert res.parser == "mineru_api" and "旧版" in res.markdown

    def down(req):
        raise httpx.ConnectError("refused")

    _mock_client(monkeypatch, down)
    res = await parsers.parse_bytes(_docx_bytes(), "r.docx", "docx")  # MinerU 不可用 → 内置兜底并注明
    assert res.parser == "builtin" and "已改用内置解析" in res.notes[0]
    with pytest.raises(parsers.ParseError, match="MinerU"):
        await parsers.parse_bytes(b"img", "a.png", "png")  # 图片无兜底


async def test_mineru_cloud_batch_flow(env, monkeypatch):
    import httpx

    from cloudsearch.core.config import get_settings
    from cloudsearch.files import parsers

    s = get_settings()
    monkeypatch.setattr(s, "mineru_cloud_token", "tok")
    monkeypatch.setattr(s, "files_parser", "mineru_cloud")
    monkeypatch.setattr(parsers.asyncio, "sleep", lambda *_: _noop())
    polls = []

    def handler(req):
        if req.url.path == "/api/v4/file-urls/batch":
            assert req.headers["authorization"] == "Bearer tok"
            return httpx.Response(200, json={"code": 0, "data": {"batch_id": "b1",
                                                                  "file_urls": ["https://oss.example/put"]}})
        if req.method == "PUT":
            assert "content-type" not in req.headers
            return httpx.Response(200)
        if req.url.path == "/api/v4/extract-results/batch/b1":
            polls.append(1)
            state = "running" if len(polls) < 2 else "done"
            return httpx.Response(200, json={"code": 0, "data": {"extract_result": [
                {"state": state, "full_zip_url": "https://cdn.example/r.zip"}]}})
        return httpx.Response(200, content=_zip("# 云端结果\n表格"))

    _mock_client(monkeypatch, handler)
    res = await parsers.parse_bytes(b"%PDF", "a.pdf", "pdf")
    assert res.parser == "mineru_cloud" and "云端结果" in res.markdown and len(polls) == 2


# ---------------------------------------------------------------- 端到端：上传 → 只基于文件回答
async def test_upload_and_answer_from_file(client, fake_llm, fake_browser):
    h = await register(client)
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    bad = await client.post(f"/api/v1/conversations/{cid}/files", headers=h,
                            files={"files": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 422
    text = "公司简介。\n本公司 2025 年营业收入 12.5 亿元，同比增长 18%。\n其他内容。".encode()
    up = await client.post(f"/api/v1/conversations/{cid}/files", headers=h,
                           files={"files": ("年报摘要.txt", text, "text/plain")})
    assert up.status_code == 201, up.text
    fid = up.json()[0]["file_id"]
    assert up.json()[0]["parse_status"] == "queued"

    # 编译智能体误判为闲聊：本条消息带了文件 → 程序改为基于文件回答，且不联网
    fake_llm.compiler_outputs.append({"kind": "chat", "reply": "好的", "conversation_title": "年报"})
    fake_llm.writer_markdown = "2025 年营业收入 12.5 亿元[1]。"
    r = await client.post(f"/api/v1/conversations/{cid}/messages", headers=h, json={
        "client_message_id": str(uuid.uuid4()), "text": "这家公司去年收入多少？", "file_ids": [fid]})
    assert r.status_code == 202, r.text
    assert parts_of(r.json()["user_message"], "file")[0]["name"] == "年报摘要.txt"
    await run_worker()

    f = (await client.get(f"/api/v1/files/{fid}", headers=h)).json()
    assert f["parse_status"] == "parsed" and f["parser"] == "builtin" and f["char_qty"] > 10
    content = (await client.get(f"/api/v1/files/{fid}/content", headers=h)).json()
    assert "12.5 亿元" in content["markdown"]
    task = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]
    assert task["task_status"] == "completed", task
    assert fake_browser.queries == [] and fake_browser.reads == []  # 没有联网
    msgs = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()
    items = msgs["items"] if isinstance(msgs, dict) else msgs
    user = next(m for m in items if m["role"] == "user")
    assert parts_of(user, "file")[0]["parse_status"] == "parsed"  # 附件状态随解析更新
    ans = next(m for m in reversed(items) if m["role"] == "assistant")
    answer = next(p for p in ans["parts"] if p["part_id"].startswith("answer-"))
    assert answer["citations"][0]["credibility_label"] == "你上传的文件"
    progress = parts_of(ans, "progress")[0]
    assert [s["key"] for s in progress["stages"]] == ["files", "extract", "verify", "write"]
    src = parts_of(ans, "source")[0]["sources"][0]
    assert src["access_method"] == "user_file" and src["file_id"] == fid
    assert "公司简介" in fake_llm.prompts["extractor"][0]
    assert "年报摘要.txt" in fake_llm.prompts["requirement_compiler"][0]

    assert (await client.delete(f"/api/v1/files/{fid}", headers=h)).status_code == 409  # 已随消息发送
    other = await register(client, "bob")
    assert (await client.get(f"/api/v1/files/{fid}", headers=other)).status_code == 404


async def test_file_plus_web_research(client, fake_llm, fake_browser):
    from conftest import quick_task_output

    h = await register(client)
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    fid = (await client.post(f"/api/v1/conversations/{cid}/files", headers=h, files={
        "files": ("计划.md", "# 参观计划\n周一去故宫。".encode(), "text/markdown")})).json()[0]["file_id"]
    out = quick_task_output()
    out["task_spec"]["scope"] = {"questions": ["计划可行吗？"], "file_ids": [fid, "file_not_mine"], "use_web": True}
    fake_llm.compiler_outputs.append(out)
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h, json={
        "client_message_id": str(uuid.uuid4()), "text": "帮我核对这个计划，故宫周一开门吗？", "file_ids": [fid]})
    await run_worker()
    task = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]
    assert task["task_status"] == "completed", task
    assert fake_browser.queries and fake_browser.reads  # 联网核实
    msgs = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()
    items = msgs["items"] if isinstance(msgs, dict) else msgs
    ans = next(m for m in reversed(items) if m["role"] == "assistant")
    srcs = parts_of(ans, "source")[0]["sources"]
    assert srcs[0]["access_method"] == "user_file" and srcs[0]["n"] == 1  # 文件排在网页之前
    assert {s["access_method"] for s in srcs} == {"user_file", "browser"}
    assert [s["key"] for s in parts_of(ans, "progress")[0]["stages"]][:3] == ["files", "plan", "search"]
