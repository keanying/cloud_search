"""报告排版与多格式导出：Markdown → HTML（自包含、内联 SVG 图表）/ PDF（浏览器打印）/ Word（python-docx）。

输入的 Markdown 中 ```chart 代码块为图表 JSON（见 agents/report_writer）。所有格式内容一致：
标题、元信息、摘要、要点、正文、图表、局限、参考来源。渲染不访问网络（浏览器上下文禁用脚本并拦截所有请求）。
"""

from __future__ import annotations

import html as _html
import io
import json
import logging
import math
import re
from typing import Any

from markdown_it import MarkdownIt

log = logging.getLogger(__name__)

PALETTE = ["#6366f1", "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6", "#0ea5e9", "#84cc16", "#ec4899"]
FONT = "'PingFang SC','Microsoft YaHei','Noto Sans CJK SC','WenQuanYi Zen Hei',sans-serif"
_CITE = re.compile(r"\[(\d{1,3})\]")


# ---------------------------------------------------------------- SVG 图表
def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.2f}"


def svg_chart(c: dict[str, Any], width: int = 720, height: int = 360) -> str:
    """bar / line / pie → 自包含 SVG（不依赖脚本，可直接嵌入 HTML/打印/转图片）。"""
    title = _html.escape(c.get("title") or "")
    unit = c.get("unit") or ""
    cats = [str(x) for x in c.get("categories", [])]
    series = c.get("series", [])
    t = c.get("type", "bar")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
           f'height="{height}" font-family="{FONT}" font-size="12">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<text x="{width / 2}" y="24" text-anchor="middle" font-size="15" font-weight="600" fill="#1e293b">'
           f'{title}</text>']
    if t == "pie":
        vals = [max(0.0, float(v or 0)) for v in (series[0]["values"] if series else [])]
        total = sum(vals) or 1.0
        cx, cy, r = width * 0.36, height / 2 + 12, min(width, height) * 0.34
        ang = -math.pi / 2
        for i, v in enumerate(vals):
            a2 = ang + 2 * math.pi * v / total
            x1, y1 = cx + r * math.cos(ang), cy + r * math.sin(ang)
            x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
            large = 1 if a2 - ang > math.pi else 0
            path = (f"M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z"
                    if v < total else f"M{cx - r},{cy} a{r},{r} 0 1,0 {2 * r},0 a{r},{r} 0 1,0 {-2 * r},0")
            out.append(f'<path d="{path}" fill="{PALETTE[i % len(PALETTE)]}" stroke="#fff" stroke-width="1.5"/>')
            ang = a2
        for i, (cat, v) in enumerate(zip(cats, vals, strict=False)):
            y = 70 + i * 24
            out.append(f'<rect x="{width * 0.68}" y="{y - 10}" width="12" height="12" rx="2" '
                       f'fill="{PALETTE[i % len(PALETTE)]}"/>')
            out.append(f'<text x="{width * 0.68 + 18}" y="{y}" fill="#334155">{_html.escape(cat)}  '
                       f'{_fmt(v)}{_html.escape(unit)}（{v / total:.1%}）</text>')
        out.append("</svg>")
        return "".join(out)

    left, right, top, bottom = 64, 24, 48, 64
    pw, ph = width - left - right, height - top - bottom
    allv = [float(v) for s in series for v in s["values"] if v is not None] or [0.0]
    vmax = max(max(allv), 0.0)
    vmin = min(min(allv), 0.0)
    if vmax == vmin:
        vmax = vmin + 1
    step = 10 ** math.floor(math.log10((vmax - vmin) / 4 or 1))
    for m in (1, 2, 2.5, 5, 10):
        if (vmax - vmin) / (step * m) <= 5:
            step *= m
            break
    lo, hi = math.floor(vmin / step) * step, math.ceil(vmax / step) * step

    def y_of(v: float) -> float:
        return top + ph - (v - lo) / (hi - lo) * ph

    tick = lo
    while tick <= hi + 1e-9:
        y = y_of(tick)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + pw}" y2="{y:.1f}" stroke="#e2e8f0"/>')
        out.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#64748b">{_fmt(tick)}</text>')
        tick += step
    if unit:
        out.append(f'<text x="{left}" y="{top - 10}" fill="#64748b">单位：{_html.escape(unit)}</text>')
    n = max(len(cats), 1)
    band = pw / n
    for i, cat in enumerate(cats):
        x = left + band * (i + 0.5)
        label = cat if len(cat) <= 8 else cat[:7] + "…"
        out.append(f'<text x="{x:.1f}" y="{top + ph + 18}" text-anchor="middle" fill="#475569">'
                   f'{_html.escape(label)}</text>')
    k = max(len(series), 1)
    for si, s in enumerate(series):
        color = PALETTE[si % len(PALETTE)]
        if t == "line":
            pts = [(left + band * (i + 0.5), y_of(float(v))) for i, v in enumerate(s["values"]) if v is not None]
            out.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" '
                       f'points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}"/>')
            for x, y in pts:
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')
        else:
            bw = band * 0.7 / k
            for i, v in enumerate(s["values"]):
                if v is None:
                    continue
                x = left + band * i + band * 0.15 + bw * si
                y0, y1 = y_of(0 if lo <= 0 <= hi else lo), y_of(float(v))
                out.append(f'<rect x="{x:.1f}" y="{min(y0, y1):.1f}" width="{bw:.1f}" height="{abs(y0 - y1):.1f}" '
                           f'rx="2" fill="{color}"/>')
                if k == 1 and n <= 12:
                    out.append(f'<text x="{x + bw / 2:.1f}" y="{min(y0, y1) - 4:.1f}" text-anchor="middle" '
                               f'font-size="11" fill="#334155">{_fmt(float(v))}</text>')
    if k > 1:
        for si, s in enumerate(series):
            x = left + si * 130
            out.append(f'<rect x="{x}" y="{height - 22}" width="12" height="12" rx="2" '
                       f'fill="{PALETTE[si % len(PALETTE)]}"/>')
            out.append(f'<text x="{x + 18}" y="{height - 12}" fill="#334155">{_html.escape(s["name"])}</text>')
    out.append("</svg>")
    return "".join(out)


def parse_chart(info: str, content: str) -> dict | None:
    if info.strip() != "chart":
        return None
    try:
        c = json.loads(content)
        return c if isinstance(c, dict) and c.get("categories") and c.get("series") else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- HTML
CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { margin: 0; background: #f6f7fb; color: #1e293b; font: 15px/1.75 %(font)s; }
.doc { max-width: 860px; margin: 32px auto; background: #fff; padding: 48px 56px; border-radius: 14px;
       box-shadow: 0 10px 30px rgba(15,23,42,.06); }
h1 { font-size: 26px; line-height: 1.35; margin: 0 0 6px; color: #0f172a; }
.meta { color: #64748b; font-size: 13px; margin-bottom: 24px; border-bottom: 1px solid #e2e8f0; padding-bottom: 14px; }
h2 { font-size: 20px; margin: 30px 0 10px; padding-left: 10px; border-left: 4px solid #6366f1; color: #0f172a; }
h3 { font-size: 17px; margin: 22px 0 8px; color: #1e293b; }
p { margin: 8px 0; }
blockquote { margin: 14px 0; padding: 12px 16px; background: #eef2ff; border-left: 4px solid #6366f1;
             border-radius: 8px; color: #312e81; }
blockquote p { margin: 4px 0; }
ul, ol { padding-left: 1.4em; }
li { margin: 4px 0; }
table { border-collapse: collapse; width: 100%%; margin: 14px 0; font-size: 14px; }
th { background: #eef2ff; color: #312e81; font-weight: 600; }
th, td { border: 1px solid #e2e8f0; padding: 8px 10px; text-align: left; vertical-align: top; }
tr:nth-child(even) td { background: #f8fafc; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 13px; }
pre { background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; border-radius: 8px; overflow-x: auto; }
figure.chart { margin: 18px 0; text-align: center; }
figure.chart svg { max-width: 100%%; height: auto; border: 1px solid #eef2f7; border-radius: 10px; }
figure.chart figcaption { color: #64748b; font-size: 12px; margin-top: 6px; }
sup.cite a { color: #6366f1; text-decoration: none; font-size: 11px; margin-left: 1px; }
.refs { margin-top: 36px; border-top: 1px solid #e2e8f0; padding-top: 12px; font-size: 13px; color: #475569; }
.refs li { margin: 6px 0; word-break: break-all; }
.refs a { color: #4f46e5; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 18px 0 22px; }
.stat { border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px 16px; background: #fbfcfe; break-inside: avoid; }
.stat .v { font-size: 26px; font-weight: 700; color: #0f172a; line-height: 1.2; font-variant-numeric: tabular-nums; }
.stat .u { font-size: 13px; color: #64748b; margin-left: 3px; font-weight: 500; }
.stat .l { font-size: 13px; color: #475569; margin-top: 4px; }
.stat sup.cite a { font-size: 11px; }
.toc { margin: 4px 0 26px; padding: 12px 16px; border: 1px dashed #cbd5e1; border-radius: 10px; font-size: 14px; }
.toc b { display: block; color: #64748b; font-size: 12px; letter-spacing: .08em; margin-bottom: 4px; }
.toc ol { margin: 0; padding-left: 1.3em; columns: 2; column-gap: 28px; }
.toc a { color: #334155; text-decoration: none; }
.cred { display: inline-block; font-size: 11px; padding: 0 6px; border-radius: 999px; background: #eef2ff;
        color: #4338ca; margin-left: 4px; }
.cred.official, .cred.academic { background: #ecfdf5; color: #047857; }
.cred.aggregate, .cred.community { background: #f8fafc; color: #64748b; }
.footer { margin-top: 24px; color: #94a3b8; font-size: 12px; }
@media print { body { background: #fff; } .doc { box-shadow: none; margin: 0; padding: 0; max-width: none; } }
""" % {"font": FONT}


def _md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")

    def fence(renderer, tokens, idx, options, env):
        tok = tokens[idx]
        chart = parse_chart(tok.info, tok.content)
        if chart is None:
            return f"<pre><code>{_html.escape(tok.content)}</code></pre>"
        cap = f"数据来源：{_html.escape(chart['source'])}" if chart.get("source") else ""
        return f'<figure class="chart">{svg_chart(chart)}<figcaption>{cap}</figcaption></figure>'

    md.add_render_rule("fence", fence)
    return md


_STATS = re.compile(r"<p><strong>关键数字</strong></p>\s*<table>.*?<tbody>(.*?)</tbody>\s*</table>", re.S)
_STAT_ROW = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td><strong>(.*?)</strong>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", re.S)
_H2 = re.compile(r"<h2>(.*?)</h2>")


def _stat_tiles(html: str) -> str:
    """把“关键数字”表格渲染成数字卡片。"""
    def tiles(m: re.Match) -> str:
        cards = "".join(f'<div class="stat"><div class="v">{v}<span class="u">{u.strip()}</span></div>'
                        f'<div class="l">{lab} {src}</div></div>' for lab, v, u, src in _STAT_ROW.findall(m.group(1)))
        return f'<div class="stats">{cards}</div>' if cards else m.group(0)
    return _STATS.sub(tiles, html)


def _toc(html: str) -> str:
    """二级标题 ≥3 个时生成目录，并给标题加锚点。"""
    heads = _H2.findall(html)
    if len(heads) < 3:
        return html
    counter = iter(range(1, len(heads) + 1))
    html = _H2.sub(lambda m: f'<h2 id="sec-{next(counter)}">{m.group(1)}</h2>', html)
    items = "".join(f'<li><a href="#sec-{i}">{re.sub(r"<[^>]+>", "", h)}</a></li>' for i, h in enumerate(heads, 1))
    at = html.find("<h2")  # 放在摘要/关键数字之后、正文第一节之前
    return html[:at] + f'<nav class="toc"><b>目录</b><ol>{items}</ol></nav>' + html[at:]


def _ref_link(src: dict) -> str:
    if src.get("access_method") == "user_file" or str(src.get("url", "")).startswith("file:"):
        return "（用户上传的文件）"
    u = _html.escape(src["url"])
    return f'<a href="{u}">{u}</a>'


def _cred_badge(src: dict) -> str:
    lab = src.get("credibility_label")
    if not lab:
        return ""
    return f' <span class="cred {_html.escape(src.get("credibility") or "")}">{_html.escape(lab)}</span>'


def render_html(*, title: str, markdown: str, sources: list[dict], meta_line: str) -> str:
    body_md = re.sub(r"^#\s+.*\n", "", markdown, count=1) if markdown.lstrip().startswith("# ") else markdown
    body = _toc(_stat_tiles(_md().render(body_md)))
    body = _CITE.sub(lambda m: f'<sup class="cite"><a href="#ref-{m.group(1)}">[{m.group(1)}]</a></sup>', body)
    refs = ""
    if sources:
        items = "".join(
            f'<li id="ref-{s["n"]}">[{s["n"]}] {_html.escape(s.get("title") or s["url"])}'
            f'{(" · " + _html.escape(s["site_name"])) if s.get("site_name") else ""}{_cred_badge(s)}'
            f'{(" · 发布 " + _html.escape(s["publish_time_text"])) if s.get("publish_time_text") else ""}<br>'
            f'{_ref_link(s)}'
            f' <span>（读取于 {_html.escape(str(s.get("retrieved_time", ""))[:16].replace("T", " "))}）</span></li>'
            for s in sources)
        refs = f'<section class="refs"><h2>参考来源</h2><ol style="list-style:none;padding:0">{items}</ol></section>'
    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_html.escape(title)}</title><style>{CSS}</style></head><body><main class=\"doc\">"
            f"<h1>{_html.escape(title)}</h1><div class=\"meta\">{_html.escape(meta_line)}</div>{body}{refs}"
            f'<div class="footer">由云搜浏览器生成 · 内容均来自实际读取的网页并标注来源 · 机器核验，未经人工审核</div>'
            f"</main></body></html>")


# ---------------------------------------------------------------- 浏览器渲染（PDF、图表图片）
async def _with_page(fn):
    """独立的短生命周期浏览器：禁用脚本、拦截所有网络请求，只渲染给定内容。不可用时返回 None。"""
    try:
        from playwright.async_api import async_playwright

        from ..browser.launch import resolve

        choice = resolve()
        if choice["mode"] in ("missing", "error"):
            return None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, **choice["launch_kwargs"])
            try:
                ctx = await browser.new_context(java_script_enabled=False, viewport={"width": 900, "height": 1200},
                                                device_scale_factor=2)
                await ctx.route("**/*", lambda route: route.abort())
                page = await ctx.new_page()
                return await fn(page)
            finally:
                await browser.close()
    except Exception as e:  # noqa: BLE001
        log.warning("browser rendering unavailable: %s", e)
        return None


async def render_pdf(html: str) -> bytes | None:
    async def fn(page):
        await page.set_content(html, wait_until="load")
        return await page.pdf(format="A4", print_background=True, prefer_css_page_size=True,
                              margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})

    return await _with_page(fn)


async def render_chart_pngs(charts: list[dict]) -> list[bytes | None]:
    if not charts:
        return []

    async def fn(page):
        out = []
        for c in charts:
            await page.set_content(f"<html><body style='margin:0'>{svg_chart(c)}</body></html>")
            out.append(await page.locator("svg").first.screenshot(type="png"))
        return out

    return await _with_page(fn) or [None] * len(charts)


# ---------------------------------------------------------------- Word
def render_docx(*, title: str, markdown: str, sources: list[dict], meta_line: str,
                chart_pngs: list[bytes | None]) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    for sec in doc.sections:
        sec.left_margin = sec.right_margin = Cm(2.2)
        sec.top_margin = sec.bottom_margin = Cm(2.0)
    for name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "Title", "List Bullet", "List Number", "Quote"):
        try:
            st = doc.styles[name]
        except KeyError:
            continue
        st.font.name = "Microsoft YaHei"
        st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "微软雅黑")
    doc.styles["Normal"].font.size = Pt(10.5)

    h = doc.add_heading(title, level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    m = doc.add_paragraph(meta_line)
    m.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    m.runs[0].font.size = Pt(9)

    body_md = re.sub(r"^#\s+.*\n", "", markdown, count=1) if markdown.lstrip().startswith("# ") else markdown
    tokens = MarkdownIt("commonmark").enable("table").parse(body_md)
    chart_iter = iter(chart_pngs)

    def add_inline(par, inline_tok):
        bold = italic = False
        for child in inline_tok.children or []:
            if child.type == "strong_open":
                bold = True
            elif child.type == "strong_close":
                bold = False
            elif child.type == "em_open":
                italic = True
            elif child.type == "em_close":
                italic = False
            elif child.type in ("text", "code_inline"):
                for piece in re.split(r"(\[\d{1,3}\])", child.content):
                    if not piece:
                        continue
                    r = par.add_run(piece)
                    r.bold, r.italic = bold, italic
                    if _CITE.fullmatch(piece):
                        r.font.superscript = True
                        r.font.color.rgb = RGBColor(0x63, 0x66, 0xF1)
                    if child.type == "code_inline":
                        r.font.name = "Consolas"
            elif child.type in ("softbreak", "hardbreak"):
                par.add_run("\n")

    i = 0
    list_stack: list[str] = []
    quote = False
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = min(int(tok.tag[1]), 3)
            p = doc.add_heading("", level=level)
            add_inline(p, tokens[i + 1])
            i += 3
            continue
        if tok.type in ("bullet_list_open", "ordered_list_open"):
            list_stack.append("List Bullet" if tok.type == "bullet_list_open" else "List Number")
        elif tok.type in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
        elif tok.type == "blockquote_open":
            quote = True
        elif tok.type == "blockquote_close":
            quote = False
        elif tok.type == "paragraph_open":
            style = list_stack[-1] if list_stack else ("Quote" if quote else None)
            p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
            add_inline(p, tokens[i + 1])
            i += 3
            continue
        elif tok.type == "fence":
            chart = parse_chart(tok.info, tok.content)
            if chart is not None:
                png = next(chart_iter, None)
                if png:
                    doc.add_picture(io.BytesIO(png), width=Cm(15.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:  # 无浏览器：用数据表代替图表
                    doc.add_paragraph(chart.get("title", ""), style="Heading 3")
                    _docx_table(doc, ["类别"] + [s["name"] for s in chart["series"]],
                                [[cat] + [("" if s["values"][j] is None else _fmt(float(s["values"][j])))
                                          for s in chart["series"]] for j, cat in enumerate(chart["categories"])])
                if chart.get("source"):
                    cap = doc.add_paragraph(f"数据来源：{chart['source']}")
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap.runs[0].font.size = Pt(8.5)
            else:
                p = doc.add_paragraph(tok.content)
                for r in p.runs:
                    r.font.name = "Consolas"
        elif tok.type == "table_open":
            rows, j = [], i + 1
            current: list[str] = []
            while tokens[j].type != "table_close":
                t = tokens[j]
                if t.type == "tr_open":
                    current = []
                elif t.type == "inline":
                    current.append(t.content)
                elif t.type == "tr_close":
                    rows.append(current)
                j += 1
            if rows:
                _docx_table(doc, rows[0], rows[1:])
            i = j + 1
            continue
        i += 1

    if sources:
        doc.add_heading("参考来源", level=2)
        for s in sources:
            p = doc.add_paragraph()
            r = p.add_run(f"[{s['n']}] {s.get('title') or s['url']}")
            r.bold = True
            extra = " · ".join(x for x in (s.get("site_name"), f"发布 {s['publish_time_text']}"
                                            if s.get("publish_time_text") else None) if x)
            p.add_run(f"{('  ' + extra) if extra else ''}\n{s['url']}").font.size = Pt(9)
    foot = doc.add_paragraph("由云搜浏览器生成 · 内容均来自实际读取的网页并标注来源 · 机器核验，未经人工审核")
    foot.runs[0].font.size = Pt(8)
    foot.runs[0].font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_table(doc, header: list[str], rows: list[list[str]]) -> None:
    from docx.shared import RGBColor

    table = doc.add_table(rows=1, cols=len(header))
    try:
        table.style = "Light Grid Accent 1"
    except Exception:  # noqa: BLE001
        table.style = "Table Grid"
    for k, text in enumerate(header):
        cell = table.rows[0].cells[k]
        cell.text = text
        for r in cell.paragraphs[0].runs:
            r.bold = True
            r.font.color.rgb = RGBColor(0x31, 0x2E, 0x81)
    for row in rows:
        cells = table.add_row().cells
        for k in range(len(header)):
            cells[k].text = row[k] if k < len(row) else ""


# ---------------------------------------------------------------- 一次生成全部格式
async def build_report_bundle(*, title: str, markdown: str, sources: list[dict], meta_line: str) -> dict[str, bytes]:
    charts = []
    for tok in MarkdownIt("commonmark").parse(markdown):
        if tok.type == "fence":
            c = parse_chart(tok.info, tok.content)
            if c is not None:
                charts.append(c)
    html = render_html(title=title, markdown=markdown, sources=sources, meta_line=meta_line)
    out: dict[str, bytes] = {"html": html.encode("utf-8"), "md": _md_with_refs(markdown, sources).encode("utf-8")}
    pngs = await render_chart_pngs(charts)
    out["docx"] = render_docx(title=title, markdown=markdown, sources=sources, meta_line=meta_line, chart_pngs=pngs)
    pdf = await render_pdf(html)
    if pdf:
        out["pdf"] = pdf
    return out


def _md_with_refs(markdown: str, sources: list[dict]) -> str:
    if not sources:
        return markdown
    lines = ["", "## 参考来源", ""]
    for s in sources:
        pub = f"，发布 {s['publish_time_text']}" if s.get("publish_time_text") else ""
        lines.append(f"[{s['n']}] {s.get('title') or s['url']} — {s['url']}{pub}")
    return markdown.rstrip() + "\n" + "\n".join(lines) + "\n"
