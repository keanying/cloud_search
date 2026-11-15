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
    assert len(doc.inline_shapes) == 2  # 封面横幅 + 图表（作为图片嵌入 Word）


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


async def test_report_figures_stages_diagram_photo(monkeypatch):
    """配图：阶段总览图（里程碑年份需在证据中）、结构示意图、来源配图（下载后内嵌）；三种导出都带图并统一编号。"""
    import io

    from cloudsearch.agents.report_writer import DiagramSpec, PhotoRef, ReportDraft, StageItem, assemble_markdown
    from cloudsearch.agents.report_writer.agent import finalize
    from cloudsearch.agents.report_writer.schemas import DiagramLayer
    from cloudsearch.orchestrator import figure_assets, report_render

    import base64

    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

    async def fake_fetch(url):
        return (png, "image/png", "png") if "shakey" in url else None

    monkeypatch.setattr(figure_assets, "fetch_image", fake_fetch)
    stored = {}

    class Store:
        async def put(self, ref, data):
            stored[ref] = data
            return ref, "h"

    monkeypatch.setattr(figure_assets, "get_storage", lambda: Store())
    ev = {1: "1950 年图灵发表论文；1956 年举行达特茅斯研究项目", 2: "1980 年 XCON 进入制造流程", 3: "2012 年 AlexNet"}
    images = {"2-1": {"url": "https://www.sri.com/shakey.jpg", "caption": "Shakey 机器人", "n": 2, "site": "SRI"},
              "3-1": {"url": "https://x.org/missing.jpg", "caption": "x", "n": 3, "site": "X"}}
    draft = ReportDraft(
        title="AI 发展史", summary="摘要[1]", markdown="## 一、早期\n\n正文[1]。\n\n[[photo:2-1]]\n\n[[diagram:d1]]\n\n[[photo:3-1]]",
        stages=[StageItem(period="1950年代", title="早期探索", milestones=["1956 达特茅斯研究项目", "1999 编造事件"], source_ns=[1]),
                StageItem(period="1980年代", title="专家系统", milestones=["1980 XCON进入制造流程"], source_ns=[2]),
                StageItem(period="2010年代", title="深度学习", milestones=["2012 AlexNet"], source_ns=[3])],
        stages_title="AI 发展的三个阶段",
        diagrams=[DiagramSpec(id="d1", title="知识获取方式如何变化？", source_ns=[1],
                              layers=[DiagramLayer(name="显式知识", nodes=["规则", "推理"]),
                                      DiagramLayer(name="统计学习", nodes=["样本", "模型"])],
                              links=["", "减少逐条获取知识的成本"]),
                  DiagramSpec(id="d2", title="没有依据的图", source_ns=[99],
                              layers=[DiagramLayer(name="a", nodes=["b"]), DiagramLayer(name="c", nodes=["d"])])],
        photos=[PhotoRef(image_id="img:2-1", caption="Shakey 与受控实验环境"), PhotoRef(image_id="9-9", caption="编造")])
    draft, used, charts = finalize(draft, valid_ns={1, 2, 3}, evidence_block="", analysis_block="",
                                   evidence_by_n=ev, images=images)
    assert [st.milestones for st in draft.stages][0] == ["1956 达特茅斯研究项目"]  # 1999 不在证据里
    assert [d.id for d in draft.diagrams] == ["d1"] and [p.image_id for p in draft.photos] == ["2-1"]
    figures, blobs = await figure_assets.build_figures("tsk1", draft, images)
    assert "figures/tsk1/photo-2-1.png" in stored and list(blobs) == ["photo-2-1.png"]
    md = assemble_markdown(draft, charts, include_title=True, figures=figures)
    assert md.count("```figure") == 2 and md.count("```photo") == 1 and "[[" not in md
    assert md.index("AI 发展的三个阶段") < md.index("## 一、早期")  # 阶段总览在正文之前
    files = await report_render.build_report_bundle(title="AI 发展史", markdown=md, sources=[], meta_line="测试",
                                                    images=blobs, subtitle="摘要")
    html = files["html"].decode()
    assert "图1｜AI 发展的三个阶段" in html and "图2｜Shakey 与受控实验环境。图片出处：SRI" in html
    assert "图3｜知识获取方式如何变化？依据来源" in html and "data:image/png;base64," in html and 'class="cover-banner"' in html
    mdout = files["md"].decode()
    assert "data:image/svg+xml;base64," in mdout and "*图2｜Shakey 与受控实验环境" in mdout
    from docx import Document

    doc = Document(io.BytesIO(files["docx"]))
    texts = "\n".join(p.text for p in doc.paragraphs)
    assert "图1｜AI 发展的三个阶段" in texts and "图2｜Shakey" in texts and "图3｜知识获取方式如何变化？" in texts
