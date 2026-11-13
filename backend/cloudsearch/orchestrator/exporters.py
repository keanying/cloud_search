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


def render_xlsx(fields: list[FieldSpec], rows: list[dict], sources: list[dict], entity: str,
                analysis: list[dict] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append([f.label for f in fields] + ["来源序号", "缺失说明"])
    for r in rows:
        missing = "; ".join(f"{k}:{MISSING_LABELS.get(v, v)}" for k, v in r["missing_reasons"].items())
        ws.append([_cell(r["values"].get(f.key)) for f in fields]
                  + [",".join(str(n) for n in r["source_nos"]), escape_cell(missing)])
    d = wb.create_sheet("字段字典")
    d.append(["字段键", "字段名", "类型", "必填", "单位", "说明"])
    for f in fields:
        d.append([f.key, f.label, f.type, "是" if f.required else "否", f.unit or "", escape_cell(f.description or "")])
    d.append([])
    d.append(["记录粒度", entity])
    d.append(["说明", "空值表示未找到可靠依据，原因见“缺失说明”；所有值均来自实际读取的网页正文"])
    s = wb.create_sheet("来源")
    s.append(["序号", "标题", "网址", "站点", "页面声明发布时间", "读取时间(UTC)", "读取方式"])
    for src in sources:
        s.append([src["n"], escape_cell(src.get("title") or ""), src.get("url"), escape_cell(src.get("site_name") or ""),
                  src.get("publish_time_text") or "未知", src.get("retrieved_time"), src.get("access_method")])
    if analysis:
        a = wb.create_sheet("分析")
        for res in analysis:
            a.append([res["title"], res["description"]])
            a.append(res["columns"])
            for row in res["rows"]:
                a.append([_cell(v) for v in row])
            if res.get("sql"):
                a.append(["计算SQL", res["sql"]])
            a.append([])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def render_json(fields: list[FieldSpec], rows: list[dict], sources: list[dict]) -> bytes:
    payload = {"fields": [f.model_dump() for f in fields], "records": rows, "sources": sources}
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def render_sources_md(sources: list[dict]) -> str:
    lines = ["## 参考来源", ""]
    for s in sources:
        pub = f"，发布：{s['publish_time_text']}" if s.get("publish_time_text") else ""
        lines.append(f"[{s['n']}] {s.get('title') or s['url']} — {s['url']}（读取：{s['retrieved_time']}{pub}）")
    return "\n".join(lines)
