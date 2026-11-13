"""产物渲染：CSV（防公式注入，UTF-8 BOM 便于 Excel）、XLSX（数据/字段字典/来源/缺失说明/分析）、JSON、Markdown。"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from openpyxl import Workbook

from ..contracts import FieldSpec

MISSING_LABELS = {"not_found": "来源未提及", "not_disclosed": "明确不公开", "not_applicable": "不适用",
                  "source_conflict": "来源冲突", "access_blocked": "访问受限", "parse_failed": "解析失败",
                  "not_requested": "未要求", "unverified": "摘录未能校验，未采用"}


def escape_cell(v: Any) -> Any:
    """防 CSV/Excel 公式注入：以 = + - @ 制表符/回车开头的文本前加单引号。"""
    if isinstance(v, str) and v and v[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _cell(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return escape_cell(v)


def render_csv(fields: list[FieldSpec], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f.label for f in fields] + ["来源序号", "缺失说明"])
    for r in rows:
        missing = "; ".join(f"{k}:{MISSING_LABELS.get(v, v)}" for k, v in r["missing_reasons"].items())
        srcs = ",".join(str(n) for n in r["source_nos"])
        w.writerow([_cell(r["values"].get(f.key)) for f in fields] + [srcs, escape_cell(missing)])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _to_number(v: Any) -> Any:
    if isinstance(v, (int, float)) or v is None:
        return v
    try:
        f = float(str(v).replace(",", "").replace("，", "").strip())
        return int(f) if f.is_integer() and abs(f) < 1e15 else f
    except ValueError:
        return v


def _style_sheet(ws, widths: dict[int, int] | None = None, *, header_row: int = 1) -> None:
    """表头样式、冻结首行、筛选、列宽自适应、自动换行。"""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    thin = Side(style="thin", color="E2E8F0")
    head_fill = PatternFill("solid", fgColor="EEF2FF")
    for cell in ws[header_row]:
        cell.font = Font(bold=True, color="312E81")
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="medium", color="6366F1"))
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
    if ws.max_row > header_row:
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(ws.max_column)}{ws.max_row}"
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        longest = max((len(str(c.value)) if c.value is not None else 0) for c in ws[letter])
        ws.column_dimensions[letter].width = (widths or {}).get(col) or min(max(10, longest * 1.6 + 2), 60)


def render_xlsx(fields: list[FieldSpec], rows: list[dict], sources: list[dict], entity: str,
                analysis: list[dict] | None = None) -> bytes:
    from openpyxl.chart import BarChart, Reference
    from openpyxl.comments import Comment
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append([f.label + (f"（{f.unit}）" if f.unit else "") for f in fields] + ["来源序号", "缺失说明"])
    missing_fill = PatternFill("solid", fgColor="FEF3C7")
    numeric = {f.key for f in fields if f.type in ("number", "integer")}
    for r in rows:
        missing = "; ".join(f"{k}:{MISSING_LABELS.get(v, v)}" for k, v in r["missing_reasons"].items())
        values = [_to_number(r["values"].get(f.key)) if f.key in numeric else _cell(r["values"].get(f.key))
                  for f in fields]
        ws.append(values + [",".join(str(n) for n in r["source_nos"]), escape_cell(missing)])
        for ci, f in enumerate(fields, start=1):  # 空值高亮并附原因批注
            if r["values"].get(f.key) is None:
                cell = ws.cell(row=ws.max_row, column=ci)
                cell.fill = missing_fill
                reason = r["missing_reasons"].get(f.key)
                if reason:
                    cell.comment = Comment(MISSING_LABELS.get(reason, reason), "云搜浏览器")
    _style_sheet(ws)

    d = wb.create_sheet("字段字典")
    d.append(["字段键", "字段名", "类型", "必填", "单位", "说明"])
    for f in fields:
        d.append([f.key, f.label, f.type, "是" if f.required else "否", f.unit or "", escape_cell(f.description or "")])
    _style_sheet(d)
    d.append([])
    d.append(["记录粒度", entity])
    d.append(["说明", "黄色空格表示未找到可靠依据（批注中有原因）；所有值均来自实际读取的网页正文，来源见“来源”表"])

    s = wb.create_sheet("来源")
    s.append(["序号", "标题", "网址", "站点", "页面声明发布时间", "读取时间(UTC)", "读取方式"])
    for src in sources:
        s.append([src["n"], escape_cell(src.get("title") or ""), src.get("url"), escape_cell(src.get("site_name") or ""),
                  src.get("publish_time_text") or "未知", src.get("retrieved_time"), src.get("access_method")])
        link = s.cell(row=s.max_row, column=3)
        if link.value:
            link.hyperlink = link.value
            link.font = Font(color="4F46E5", underline="single")
    _style_sheet(s, {3: 50})

    if analysis:
        a = wb.create_sheet("分析")
        row_no = 1
        for res in analysis:
            if not res.get("columns"):
                continue
            a.cell(row=row_no, column=1, value=res["title"]).font = Font(bold=True, size=13, color="0F172A")
            a.cell(row=row_no + 1, column=1, value=res["description"]).font = Font(color="64748B")
            head = row_no + 2
            for ci, col in enumerate(res["columns"], start=1):
                c = a.cell(row=head, column=ci, value=col)
                c.font = Font(bold=True, color="312E81")
                c.fill = PatternFill("solid", fgColor="EEF2FF")
            for ri, r in enumerate(res["rows"], start=head + 1):
                for ci, v in enumerate(r, start=1):
                    a.cell(row=ri, column=ci, value=_cell(v))
            last = head + len(res["rows"])
            num_cols = [ci for ci in range(2, len(res["columns"]) + 1)
                        if all(isinstance(r[ci - 1], (int, float)) or r[ci - 1] is None for r in res["rows"])]
            if res["rows"] and num_cols and len(res["rows"]) <= 30:  # 原生 Excel 图表，可直接编辑
                ch = BarChart()
                ch.title = res["title"]
                ch.height, ch.width = 7.5, 16
                ch.add_data(Reference(a, min_col=num_cols[0], max_col=num_cols[-1], min_row=head, max_row=last),
                            titles_from_data=True)
                ch.set_categories(Reference(a, min_col=1, min_row=head + 1, max_row=last))
                a.add_chart(ch, f"{chr(ord('A') + len(res['columns']) + 1)}{row_no}")
            row_no = max(last + 2, row_no + 18 if res["rows"] and num_cols else last + 2)
        for col in "ABCDEF":
            a.column_dimensions[col].width = 18
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def analysis_markdown(analysis: list[dict]) -> str:
    """把计算结果整理成 Markdown 表格 + 图表（数据直接来自程序计算）。"""
    import json as _json

    parts = []
    for res in analysis:
        cols, rows = res.get("columns") or [], res.get("rows") or []
        if not cols:
            continue
        parts.append(f"### {res['title']}\n\n{res.get('description') or ''}\n")
        if not rows:
            parts.append("（无数据）")
            continue
        parts.append("| " + " | ".join(str(c) for c in cols) + " |\n|" + "---|" * len(cols))
        parts.append("\n".join("| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows[:50]))
        num_cols = [i for i in range(1, len(cols)) if all(isinstance(r[i], (int, float)) or r[i] is None for r in rows)]
        if num_cols and 2 <= len(rows) <= 20:
            chart = {"type": "bar", "title": res["title"], "unit": None, "categories": [str(r[0]) for r in rows],
                     "series": [{"name": str(cols[i]), "values": [r[i] for r in rows]} for i in num_cols[:3]],
                     "source": "程序计算（DuckDB）"}
            parts.append("```chart\n" + _json.dumps(chart, ensure_ascii=False) + "\n```")
    return "\n\n".join(parts)


def render_json(fields: list[FieldSpec], rows: list[dict], sources: list[dict]) -> bytes:
    payload = {"fields": [f.model_dump() for f in fields], "records": rows, "sources": sources}
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def render_sources_md(sources: list[dict]) -> str:
    lines = ["## 参考来源", ""]
    for s in sources:
        pub = f"，发布：{s['publish_time_text']}" if s.get("publish_time_text") else ""
        lines.append(f"[{s['n']}] {s.get('title') or s['url']} — {s['url']}（读取：{s['retrieved_time']}{pub}）")
    return "\n".join(lines)
