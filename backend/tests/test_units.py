from __future__ import annotations

import pytest

from cloudsearch.agents.analyst import Analysis, Filter, InvalidAnalysis, Metric, run_analysis
from cloudsearch.agents.report_writer import sanitize_citations
from cloudsearch.agents.requirement_compiler import IntentDecision, normalize_decision
from cloudsearch.agents.verifier import locate_quote
from cloudsearch.browser.guard import UrlNotAllowed, check_url
from cloudsearch.browser.reader import looks_blocked
from cloudsearch.contracts import FieldSpec, SearchHit
from cloudsearch.orchestrator.exporters import escape_cell, render_csv
from cloudsearch.search.engines import decode_bing_url, looks_relevant
from cloudsearch.search.service import rank_hits


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.5/x", "http://169.254.169.254/latest/meta-data",
                                 "http://localhost:8000/", "file:///etc/passwd", "http://[::1]/",
                                 "http://192.168.1.1/", "javascript:alert(1)", "http://example.com:22/"])
async def test_ssrf_guard_blocks(url, env):
    with pytest.raises(UrlNotAllowed):
        await check_url(url)


def test_locate_quote_tolerates_whitespace():
    text = "故宫博物院 每周一闭馆\n（法定节假日除外）。"
    assert locate_quote(text, "每周一闭馆 （法定节假日除外）") == (6, 21)
    assert locate_quote(text, "每周二闭馆") is None
    assert locate_quote(text, "故宫") is None  # 过短不作为证据


def test_sanitize_citations():
    md, used = sanitize_citations("甲[1]。乙[2，7]。丙[9]", {1, 2})
    assert md == "甲[1]。乙[2]。丙" and used == [1, 2]


def test_csv_formula_injection_escaped():
    assert escape_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert escape_cell("-5") == "'-5" and escape_cell(5) == 5
    data = render_csv([FieldSpec(key="a", label="A")],
                      [{"values": {"a": "@SUM(1)"}, "missing_reasons": {}, "source_nos": [1]}])
    assert "'@SUM(1)" in data.decode("utf-8-sig")


def test_analysis_rejects_unknown_or_non_numeric_fields():
    fields = [FieldSpec(key="city", label="城市"), FieldSpec(key="price", label="票价", type="number")]
    with pytest.raises(InvalidAnalysis):
        run_analysis([], fields, Analysis(title="t", description="d", metrics=[Metric(func="sum", field="city",
                                                                                         alias="x")]))
    with pytest.raises(InvalidAnalysis):
        run_analysis([], fields, Analysis(title="t", description="d", metrics=[Metric(func="count", field="x;drop",
                                                                                         alias="x")]))
    res = run_analysis([{"city": "北京", "price": "1,200"}, {"city": "上海", "price": "abc"}], fields,
                       Analysis(title="t", description="d", metrics=[Metric(func="sum", field="price", alias="合计")],
                                filters=[Filter(field="city", op="contains", value="'; DROP TABLE t; --")]))
    assert res.rows == [[None]]  # 参数绑定，注入字符串只是普通值
    res = run_analysis([{"city": "北京", "price": "1,200"}, {"city": "上海", "price": "abc"}], fields,
                       Analysis(title="t", description="d", metrics=[Metric(func="sum", field="price", alias="合计")]))
    assert res.rows == [[1200.0]] and res.warnings  # 无法解析的数字按空值处理并告警


def test_compiler_normalization_enforces_mode_and_confirmation():
    d = IntentDecision.model_validate({"kind": "task", "reply": "好的", "task_spec": {
        "mode": "quick_search", "title": "t", "requirement_text": "查一下", "scope": {}}})
    d = normalize_decision(d, "research")
    assert d.task_spec.mode == "research" and d.task_spec.report is not None
    assert d.task_spec.output_formats == ["md"]
    d2 = IntentDecision.model_validate({"kind": "task", "reply": "好的", "task_spec": {
        "mode": "dataset", "title": "t", "requirement_text": "采集", "scope": {}}})
    d2 = normalize_decision(d2, "auto")
    assert d2.kind == "clarify" and d2.task_spec is None  # 没有字段定义不能开跑
    d3 = IntentDecision.model_validate({"kind": "task", "reply": "x"})
    assert normalize_decision(d3, "auto").kind == "clarify"


def test_search_helpers():
    assert decode_bing_url("https://www.bing.com/ck/a?!&&p=x&u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9hP2I9MQ&ntb=1") == \
        "https://example.com/a?b=1"
    junk = [SearchHit(engine="b", query="q", rank=i, url="https://www.google.com/", title="Google") for i in range(5)]
    assert not looks_relevant("故宫博物院 开放时间", junk)
    decoy = [SearchHit(engine="b", query="q", rank=i, url=f"https://jingyan.baidu.com/{i}",
                       title="东芝打印机扫描文件在电脑哪里找", snippet="2024年 扫描时间设置方法") for i in range(5)]
    assert not looks_relevant("故宫博物院 开放时间 官网", decoy)  # 只共享“时间”这类常见词不算相关
    good = [SearchHit(engine="b", query="q", rank=1, url="https://www.dpm.org.cn/Visit.html", title="导览 - 故宫博物院",
                      snippet="故宫博物院开放时间"),
            SearchHit(engine="b", query="q", rank=2, url="https://x.cn", title="故宫开放时间 2026", snippet=None),
            SearchHit(engine="b", query="q", rank=3, url="https://y.cn", title="别的", snippet=None)]
    assert looks_relevant("故宫博物院 开放时间 官网", good)
    hits = [SearchHit(engine="b", query=q, rank=r, url=f"https://{q}-{r}.com/", title="t")
            for q in ("q1", "q2") for r in (1, 2, 3)]
    picked = rank_hits(hits, 4)
    assert [h.query for h in picked] == ["q1", "q2", "q1", "q2"]  # 查询间交错
    many = [SearchHit(engine="b", query="q", rank=r, url=f"https://same.com/{r}", title="t") for r in range(1, 6)]
    assert len(rank_hits(many, 5)) == 3  # 同域名最多 3 条


def test_block_detection():
    assert looks_blocked("https://x.com/captcha?r=1", "验证", "请完成验证")
    assert looks_blocked("https://x.com/a", "百度安全验证", "网络不给力，请稍后重试")
    assert not looks_blocked("https://x.com/a", "正常文章", "这是一篇很长的文章。" * 200)
