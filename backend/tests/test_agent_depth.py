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
