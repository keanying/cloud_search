"""智能体深化：来源可信度、长文段落挑选、关键数字核对、子问题拆解与多轮覆盖补查、引用增强与追问建议。"""

from __future__ import annotations

import uuid

from conftest import parts_of, quick_task_output, register, run_worker


# ---------------------------------------------------------------- 单元
def test_credibility_tiers():
    from cloudsearch.search import credibility as cr

    assert cr.classify("https://www.stats.gov.cn/sj/") == "official"
    assert cr.classify("https://www.dpm.org.cn/visit", preferred=["dpm.org.cn"]) == "official"
    assert cr.classify("https://arxiv.org/abs/2401.1") == "academic"
    assert cr.classify("https://www.thepaper.cn/news") == "media"
    assert cr.classify("https://zh.wikipedia.org/wiki/x") == "reference"
    assert cr.classify("https://zhuanlan.zhihu.com/p/1") == "community"
    assert cr.classify("https://baijiahao.baidu.com/s?id=1") == "aggregate"
    assert cr.classify("https://unknown-blog.example/") == "unknown"
    assert cr.score("https://www.gov.cn/") > cr.score("https://zhihu.com/") > cr.score("https://wenku.baidu.com/x")
    assert cr.label("https://news.cn/a") == "权威媒体"


def test_select_passages_keeps_relevant_parts():
    from cloudsearch.agents.extractor.passages import select_passages

    filler = "这是一段与问题无关的填充文字，介绍了网站导航和版权信息。\n" * 400
    key = "故宫博物院2025年接待观众1700万人次，同比增长5%。\n"
    text = "标题：年度报告\n" + filler + key + filler
    out = select_passages(text, ["故宫 观众人次", "接待观众"], budget=3000, chunk=600)
    assert len(out) < len(text) / 4
    assert "1700万人次" in out and out.startswith("标题：年度报告")
    assert "略去约" in out
    assert select_passages("短文本", ["x"], budget=100) == "短文本"


def test_verify_highlights_and_markdown():
    from cloudsearch.agents.report_writer import Highlight, ReportDraft, assemble_markdown, verify_highlights

    ev = {1: "故宫2025年接待观众 1,700 万人次", 2: "票价 60 元"}
    items = [Highlight(label="观众", value="1,700", unit="万人次", source_n=1),
             Highlight(label="编造", value="999", source_n=1),
             Highlight(label="票价", value="60", unit="元", source_n=1),  # 数字在别的来源，不算
             Highlight(label="票价", value="60", unit="元", source_n=2)]
    kept = verify_highlights(items, ev, "")
    assert [(h.label, h.source_n) for h in kept] == [("观众", 1), ("票价", 2)]
    md = assemble_markdown(ReportDraft(title="t", markdown="正文[1]", highlights=kept), [], include_title=True,
                           with_highlights=True)
    assert "| 观众 | **1,700** 万人次 | [1] |" in md


# ---------------------------------------------------------------- 流程
async def _run(client, h, fake_llm, out: dict, text: str):
    fake_llm.compiler_outputs.append(out)
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": text})
    await run_worker()
    task = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]
    msgs = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()
    items = msgs["items"] if isinstance(msgs, dict) else msgs
    return task, next(m for m in reversed(items) if m["role"] == "assistant")


async def test_answer_has_highlights_rich_citations_and_suggestions(client, fake_llm, fake_browser):
    fake_llm.writer_extra = {
        # 只有故宫页面（a）的证据含 60：另一个来源上的同一数字、以及编造的数字都会被程序剔除
        "highlights": [{"label": "门票", "value": "60", "unit": "元", "source_n": 1},
                       {"label": "门票", "value": "60", "unit": "元", "source_n": 2},
                       {"label": "编造", "value": "12345", "source_n": 1}],
        "follow_ups": ["故宫需要提前几天预约？", "  ", "故宫夜场什么时候开放？", "故宫有学生票吗？", "多余的第四个"]}
    fake_llm.extract_two = True
    h = await register(client)
    task, msg = await _run(client, h, fake_llm, quick_task_output(), "故宫什么时候开放？")
    assert task["task_status"] == "completed", task
    hl = parts_of(msg, "highlights")[0]["items"]
    assert [x["value"] for x in hl] == ["60"] and hl[0]["url"] == "https://a.example.com/1"
    sug = parts_of(msg, "suggestions")[0]["items"]
    assert sug == ["故宫需要提前几天预约？", "故宫夜场什么时候开放？", "故宫有学生票吗？"]
    answer = next(p for p in msg["parts"] if p["part_id"].startswith("answer-"))
    cit = answer["citations"][0]
    assert cit["quote"] and cit["credibility_label"] and "site_name" in cit
    src = parts_of(msg, "source")[0]["sources"][0]
    assert src["credibility"] in ("official", "unknown") and src["credibility_label"]
    writer_prompt = fake_llm.prompts["report_writer"][0]
    assert "今天日期" in writer_prompt and "一般网站" in writer_prompt


async def test_research_sub_questions_drive_multi_wave_coverage(client, fake_llm, fake_browser):
    fake_llm.plan_output = {
        "intent": "了解故宫的开放安排与票价", "key_entities": ["故宫博物院"], "preferred_sources": [],
        "sub_questions": ["开放时间", "票价"],
        "queries": [{"query": "故宫 开放时间", "purpose": "开放时间", "language": "zh"}]}
    fake_llm.coverage_outputs = [
        # 模型误判“充分”：程序发现“票价”子问题没有任何证据，强制补查
        {"sufficient": True, "aspects": [], "missing_aspects": [], "extra_queries": []},
        {"sufficient": True, "aspects": [], "missing_aspects": [], "extra_queries": []},
    ]
    out = quick_task_output(mode="research")
    out["task_spec"]["limits"] = {"max_queries": 4, "max_sources": 1}
    out["task_spec"]["report"] = {"question": "故宫开放时间和票价"}
    h = await register(client)
    task, msg = await _run(client, h, fake_llm, out, "调研一下故宫开放时间和票价")
    assert task["task_status"] == "completed", task
    submitted = [q.query for q in fake_browser.queries]
    assert "票价" in submitted  # 空缺子问题被强制补查
    assert len(fake_browser.reads) == 2  # 第二轮读到了新来源
    assert fake_llm.calls["coordinator"] == 2  # 第二轮评估后无新查询，停止
    cov_prompt = fake_llm.prompts["coordinator"][0]
    assert "票价" in cov_prompt and "开放时间" in cov_prompt
    writer_prompt = fake_llm.prompts["report_writer"][0]
    assert "开放时间；票价" in writer_prompt  # 子问题作为报告提纲
    progress = parts_of(msg, "progress")[0]
    cov = next(s for s in progress["stages"] if s["key"] == "coverage")
    assert cov["status"] == "done"


async def test_follow_up_sees_previous_answer_and_sources(client, fake_llm, fake_browser):
    fake_llm.writer_markdown = "故宫每周一闭馆[1]。" + "详细说明。" * 300
    h = await register(client)
    fake_llm.compiler_outputs.append(quick_task_output())
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    for text in ("故宫什么时候开放？", "那第二点展开说说"):
        await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                          json={"client_message_id": str(uuid.uuid4()), "text": text})
        await run_worker()
    prompt = fake_llm.prompts["requirement_compiler"][-1]
    assert "来源：[1]" in prompt and "example.com" in prompt
    assert prompt.count("详细说明。") > 160  # 最近的回答保留较完整（>800 字）
    assert "用户最新消息：那第二点展开说说" in prompt


async def test_report_streams_live_draft_and_records_timing(client, fake_llm, fake_browser):
    """撰写时边写边显示（draft 片段逐步变长），完成后由最终成果替代；任务与各阶段耗时被记录。"""
    from sqlalchemy import select

    from cloudsearch.db.base import session_scope
    from cloudsearch.db.models import ConversationEvent

    fake_llm.stream_writer = True
    fake_llm.writer_markdown = "## 一、开放安排\n故宫每周一闭馆[1]。" + "补充说明。" * 60
    h = await register(client)
    task, msg = await _run(client, h, fake_llm, quick_task_output(), "故宫什么时候开放？")
    assert task["task_status"] == "completed", task
    async with session_scope() as s:
        events = (await s.execute(select(ConversationEvent).where(
            ConversationEvent.event_type == "message_updated").order_by(ConversationEvent.event_seq_no))).scalars().all()
    drafts = [p for e in events for p in e.event_json.get("parts", []) if p.get("type") == "draft"]
    assert len(drafts) >= 2 and drafts[-1]["chars"] > drafts[0]["chars"]  # 逐步变长
    assert drafts[0]["status"] == "writing" and "开放安排" in drafts[-1]["text"]
    assert not [p for p in msg["parts"] if p["type"] == "draft"]  # 最终消息里不再有草稿
    progress = parts_of(msg, "progress")[0]
    m = progress["metrics"]
    assert m["elapsed_ms"] >= 500 and m["finished_ms"] and m["llm_requests"] >= 4
    write = next(st for st in progress["stages"] if st["key"] == "write")
    assert write["elapsed_ms"] >= 500  # 流式撰写约若干个 0.25s 片段


async def test_streamed_writer_retries_after_invalid_output(client, fake_llm, fake_browser):
    """流式撰写时第一次输出校验失败：自动重试并完成（此前 run_stream 不支持重试，任务会失败）。"""
    fake_llm.stream_writer = True
    fake_llm.writer_invalid_first = True
    h = await register(client)
    task, msg = await _run(client, h, fake_llm, quick_task_output(), "故宫什么时候开放？")
    assert task["task_status"] == "completed", task
    assert fake_llm.calls["report_writer"] == 2
    assert any(p["part_id"].startswith("answer-") for p in msg["parts"])


async def test_clarification_offers_options(client, fake_llm, fake_browser):
    """澄清问题带候选选项（去重、去掉“其他”、最多 5 个）；只有问题文字时也能回答。"""
    fake_llm.compiler_outputs.append({
        "kind": "clarify", "reply": "范围很大，先确认几点。", "conversation_title": "副业渠道",
        "questions": ["每周能投入多少时间？", "倾向哪类副业？"],
        "clarify_items": [
            {"question": "每周能投入多少时间？", "options": ["5 小时以内", "10 小时左右", "20 小时以上", "其他"]},
            {"question": "倾向哪类副业？", "options": ["线上兼职", "技能接单", "内容变现", "技能接单", "小生意",
                                                  "电商", "其它"], "multi": True}]})
    h = await register(client)
    task, msg = None, None
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "副业渠道"})
    await run_worker()
    msgs = (await client.get(f"/api/v1/conversations/{cid}/messages", headers=h)).json()
    items = msgs["items"] if isinstance(msgs, dict) else msgs
    part = parts_of(next(m for m in reversed(items) if m["role"] == "assistant"), "clarification")[0]
    assert part["questions"] == ["每周能投入多少时间？", "倾向哪类副业？"]
    assert part["items"][0] == {"question": "每周能投入多少时间？", "multi": False,
                                "options": ["5 小时以内", "10 小时左右", "20 小时以上"]}
    assert part["items"][1]["multi"] is True
    assert part["items"][1]["options"] == ["线上兼职", "技能接单", "内容变现", "小生意", "电商"]


async def test_sectioned_report_chapters_timeline_and_checks(monkeypatch):
    """深度报告：逐章撰写（中文编号、各章图表编号不冲突）、综合分析章、时间轴按证据核对年份、无效引用被清理。"""
    from cloudsearch.agents.report_writer import agent as rw
    from cloudsearch.agents.report_writer.schemas import (ChartSeries, ChartSpec, ReportDraft, SectionDraft,
                                                          TimelineItem)

    prompts: list[str] = []
    partials: list[str] = []

    async def fake_run(spec, prompt, ctx=None, on_partial=None, **kw):
        prompts.append(prompt)
        if spec is rw.SECTION_SPEC:
            i = int(prompt.split("编号为“")[1][0] == "二")  # 0 → 第一章，1 → 第二章
            if on_partial:
                await on_partial(SectionDraft(heading=f"阶段{i + 1}", markdown="写作中…"))
            chart = ChartSpec(id="c1", type="bar", title=f"图{i}", categories=["a", "b"],
                              series=[ChartSeries(name="x", values=[15.3, 26.2] if i == 0 else [99.0, 1.0])])
            return SectionDraft(heading=f"阶段{i + 1}：年代", markdown=f"### 小节\n\n事实一[1]，事实二[9]。\n\n[[chart:c1]]",
                                charts=[chart])
        assert "## 三、综合分析" in prompt and "## 一、阶段1：年代" in prompt and "## 二、阶段2：年代" in prompt
        return ReportDraft(title="发展史", summary="摘要[2]", key_points=["要点[1]"],
                           markdown="### 主线\n\n综合判断[2]。",
                           timeline=[TimelineItem(date="2012", title="AlexNet", source_n=1),
                                     TimelineItem(date="1956年", title="达特茅斯会议", source_n=2),
                                     TimelineItem(date="2030", title="编造的事件", source_n=1)],
                           limitations=[], follow_ups=["后续？"])

    monkeypatch.setattr(rw, "run_agent", fake_run)

    async def on_partial(d):
        partials.append(d.markdown)

    evidence_by_n = {1: "2012 年 AlexNet 的 top-5 错误率为 15.3%，第二名为 26.2%", 2: "1956 年举行达特茅斯研究项目"}
    draft, used, charts = await rw.write_sectioned(
        question="AI 发展史", sections=["早期探索", "深度学习"], section_evidence=["[1] …", "[2] …"],
        audience=None, evidence_block="\n".join(evidence_by_n.values()), valid_ns={1, 2}, analysis_block="",
        conflicts_block="", gaps_block="", ctx=None, today="2026-11-15", evidence_by_n=evidence_by_n,
        on_partial=on_partial)
    md = draft.markdown
    assert md.index("## 一、阶段1：年代") < md.index("## 二、阶段2：年代") < md.index("## 三、综合分析")
    assert "[9]" not in md and "事实二。" in md  # 不存在的来源序号被删除
    assert [c.id for c in charts] == ["s1_c1"]  # 第二章图表数字核对不上被删除，编号带章前缀
    assert "[[chart:s1_c1]]" in md
    assert [t.title for t in draft.timeline] == ["达特茅斯会议", "AlexNet"]  # 2030 不在证据里，按年份排序
    assert used == [1, 2] and partials and "写作中" in partials[0]
    full = rw.assemble_markdown(draft, charts, include_title=True)
    assert "```timeline" in full and full.index("```timeline") < full.index("## 一、")


async def test_research_task_writes_chapters(client, fake_llm, fake_browser, monkeypatch):
    """研究任务走分章撰写：每个子问题一章（中文编号）+ 综合分析，报告文件包含全部章节。"""
    from cloudsearch.orchestrator import pipeline

    monkeypatch.setattr(pipeline.Pipeline, "_deep_report", lambda self, sections, n: True)
    fake_llm.plan_output = {**fake_llm.plan_output, "sub_questions": ["开放时间", "票价", "预约方式"]}
    h = await register(client)
    fake_llm.compiler_outputs.append(quick_task_output(mode="research"))
    cid = (await client.post("/api/v1/conversations", json={}, headers=h)).json()["conversation_id"]
    await client.post(f"/api/v1/conversations/{cid}/messages", headers=h,
                      json={"client_message_id": str(uuid.uuid4()), "text": "研究一下故宫开放规则"})
    await run_worker()
    task = (await client.get(f"/api/v1/conversations/{cid}/tasks", headers=h)).json()[0]
    assert task["task_status"] == "completed", task
    writer_prompts = fake_llm.prompts["report_writer"]
    assert sum("本章要回答：" in p for p in writer_prompts) == 3 and "已写好的各章正文" in writer_prompts[-1]
    arts = (await client.get("/api/v1/artifacts", headers=h)).json()
    md_art = next(a for a in arts if a["display_name"].endswith(".md"))
    text = (await client.get(f"/api/v1/artifacts/{md_art['artifact_id']}/download", headers=h)).text
    for heading in ("## 一、章节开放时间", "## 二、章节票价", "## 三、章节预约方式", "## 四、综合分析"):
        assert heading in text, heading
