"""报告排版与导出：图表数据核对、组装顺序、HTML/Word/PDF 内容。"""

from __future__ import annotations

import io

import pytest

from cloudsearch.agents.report_writer import ChartSpec, ReportDraft, assemble_markdown, verify_charts
from cloudsearch.orchestrator import report_render

EVIDENCE = "[1] 故宫博物院 2024 年接待观众 1,700 万人次；2023 年为 1,500 万人次。\n[2] 国家博物馆 2024 年 900 万人次。"
SOURCES = [{"n": 1, "title": "故宫年报", "url": "https://www.dpm.org.cn/report", "site_name": "故宫博物院",
            "publish_time_text": "2025-01-10", "retrieved_time": "2026-11-13T10:00:00.000Z"},
           {"n": 2, "title": "国博简介", "url": "https://www.chnmuseum.cn/", "site_name": None,
            "publish_time_text": None, "retrieved_time": "2026-11-13T10:01:00.000Z"}]


def _chart(values, cid="c1"):
    return ChartSpec(id=cid, type="bar", title="2024 年观众人次", unit="万人次", categories=["故宫", "国博"],
                     series=[{"name": "人次", "values": values}], source="来源[1][2]")


def test_chart_values_must_appear_in_evidence():
    ok, dropped = verify_charts([_chart([1700, 900]), _chart([1700, 950], "c2")], EVIDENCE)
    assert [c.id for c in ok] == ["c1"] and dropped == ["2024 年观众人次"]  # 950 在证据中不存在 → 删除
    bad_shape, dropped2 = verify_charts([_chart([1700])], EVIDENCE)  # 数值个数与类别不一致
    assert bad_shape == [] and dropped2


def _draft():
    return ReportDraft(title="博物馆观众情况", summary="2024 年故宫接待观众 1,700 万人次[1]。",
                       key_points=["故宫人次高于国博[1][2]"],
                       markdown="## 对比\n\n| 博物馆 | 人次 |\n|---|---|\n| 故宫 | 1700 万[1] |\n| 国博 | 900 万[2] |\n\n"
                                "[[chart:c1]]\n\n> 注意：口径为全年。",
                       charts=[_chart([1700, 900])], limitations=["仅统计两家"])


def test_assemble_order_and_chart_placement():
    md = assemble_markdown(_draft(), [_chart([1700, 900])], include_title=True)
    order = [md.index(x) for x in ("# 博物馆观众情况", "**摘要**", "**要点**", "## 对比", "```chart", "## 局限与说明")]
    assert order == sorted(order) and "[[chart:" not in md


async def test_bundle_formats_and_content():
    md = assemble_markdown(_draft(), [_chart([1700, 900])], include_title=True)
    files = await report_render.build_report_bundle(title="博物馆观众情况", markdown=md, sources=SOURCES,
                                                    meta_line="研究报告 · 测试")
    html = files["html"].decode()
    assert "<svg" in html and "2024 年观众人次" in html and "<script" not in html.lower()
    assert 'href="#ref-1"' in html and 'id="ref-2"' in html and "<table>" in html
    assert "参考来源" in files["md"].decode()
    from docx import Document

    doc = Document(io.BytesIO(files["docx"]))
    texts = "\n".join(p.text for p in doc.paragraphs)
    assert "博物馆观众情况" in texts and "参考来源" in texts and "要点" in texts
    assert len(doc.tables) >= 1 and doc.tables[0].rows[1].cells[0].text == "故宫"
    from cloudsearch.browser.launch import resolve

    if resolve()["mode"] in ("missing", "error"):
        pytest.skip("无浏览器：PDF 与图表图片跳过")
    assert files["pdf"][:4] == b"%PDF" and len(files["pdf"]) > 10_000
    assert len(doc.inline_shapes) == 1  # 图表已作为图片嵌入 Word


def test_svg_chart_types():
    for t in ("bar", "line", "pie"):
        svg = report_render.svg_chart({"type": t, "title": "t", "unit": "个", "categories": ["a", "b", "c"],
                                       "series": [{"name": "s1", "values": [1, 2.5, None]},
                                                  {"name": "s2", "values": [3, 1, 2]}]})
        assert svg.startswith("<svg") and svg.endswith("</svg>")


def test_html_stat_tiles_toc_and_credibility():
    from cloudsearch.orchestrator.report_render import render_html

    md = ("> **摘要**　x\n\n**关键数字**\n\n| 指标 | 数值 | 来源 |\n|---|---|---|\n| 观众 | **1,700** 万人次 | [1] |\n\n"
          "## 一\na[1]\n## 二\nb\n## 三\nc\n")
    h = render_html(title="T", markdown=md, meta_line="m", sources=[
        {"n": 1, "url": "https://a.cn", "title": "A", "credibility": "official", "credibility_label": "官方"}])
    assert '<div class="stats">' in h and '<span class="u">万人次</span>' in h and "<table>" not in h
    assert h.index('<nav class="toc">') > h.index('<div class="stats">')
    assert '<h2 id="sec-3">' in h and 'class="cred official">官方' in h
