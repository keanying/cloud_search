"""结构化数据文件（JSON / JSONL / CSV / TSV / Excel）：由程序计算准确的统计概览，而不是让模型逐块阅读。

解析结果 = 「数据概览（程序统计）」+「数据记录」两部分：
- 概览：记录数、字段与类型、缺失/空值、不同值个数、类别字段的取值分布、文本长度、数值统计、重复记录与重复值、均匀抽样的样例；
  数字全部由程序计算，作为来源被引用时可逐字核对。
- 记录：每条一行（紧凑 JSON），用于回答具体记录的问题；长文件在任务中按相关度挑选部分阅读。
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from typing import Any

MAX_ROWS = 200_000
TOP_N = 12


def _flatten(rec: Any, prefix: str = "") -> dict[str, Any]:
    """对象展开一层嵌套（a.b）；非对象记录包成 {"value": ...}。"""
    if not isinstance(rec, dict):
        return {prefix or "value": rec}
    out: dict[str, Any] = {}
    for k, v in rec.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and not prefix:
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def find_records(data: Any) -> tuple[list, str]:
    """在 JSON 中找到“记录列表”：顶层数组，或对象里最大的对象数组。返回 (记录, 路径说明)。"""
    if isinstance(data, list):
        return data, "顶层数组"
    if isinstance(data, dict):
        best, path = None, ""
        stack = [(data, "")]
        while stack:
            node, p = stack.pop()
            for k, v in node.items():
                kp = f"{p}.{k}" if p else k
                if isinstance(v, list) and v and isinstance(v[0], dict) and (best is None or len(v) > len(best)):
                    best, path = v, kp
                elif isinstance(v, dict) and p.count(".") < 3:
                    stack.append((v, kp))
        if best is not None:
            return best, f"字段 {path}"
        return [data], "单个对象"
    return [data], "单个值"


def load_json_records(text: str) -> tuple[list, str] | None:
    try:
        return find_records(json.loads(text))
    except ValueError:
        pass
    rows = []  # JSONL：每行一个 JSON
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            return None
    return (rows, "每行一条（JSONL）") if rows else None


def _kind(v: Any) -> str:
    if v is None or v == "":
        return "空"
    if isinstance(v, bool):
        return "布尔"
    if isinstance(v, (int, float)):
        return "数值"
    if isinstance(v, list):
        return "数组"
    if isinstance(v, dict):
        return "对象"
    s = str(v).strip()
    try:
        float(s.replace(",", ""))
        return "数值"
    except ValueError:
        return "文本"


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}"


def _cell(v: Any, limit: int = 80) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = s.replace("\n", " ").replace("|", "\\|")
    return s if len(s) <= limit else s[:limit] + "…"


def profile_records(records: list, *, name: str, where: str = "") -> str:
    total = len(records)
    rows = [_flatten(r) for r in records[:MAX_ROWS]]
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    lines = [f"# 数据概览（程序统计，{name}）", ""]
    lines.append(f"- 记录总数：{total:,} 条" + (f"（统计了前 {MAX_ROWS:,} 条）" if total > MAX_ROWS else ""))
    if where:
        lines.append(f"- 记录位置：{where}")
    lines.append(f"- 字段数：{len(cols)} 个：{'、'.join(cols[:60])}")
    keyed = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]
    dup = len(keyed) - len(set(keyed))
    lines.append(f"- 完全重复的记录：{dup:,} 条")
    lines += ["", "## 字段统计", "", "| 字段 | 类型 | 非空 | 缺失/空值 | 不同值 | 说明 |", "|---|---|---|---|---|---|"]
    details: list[str] = []
    for c in cols:
        vals = [r.get(c) for r in rows]
        kinds = Counter(_kind(v) for v in vals)
        empty = kinds.pop("空", 0)
        kind = kinds.most_common(1)[0][0] if kinds else "空"
        if len(kinds) > 1:
            kind += "（混合：" + "、".join(f"{k}{n}" for k, n in kinds.most_common()) + "）"
        present = [v for v in vals if v is not None and v != ""]
        hashed = [_cell(v, 10_000) for v in present]
        distinct = len(set(hashed))
        note = ""
        if kind.startswith("数值"):
            nums = [n for n in (_num(v) for v in present) if n is not None]
            if nums:
                note = (f"最小 {_fmt(min(nums))}，最大 {_fmt(max(nums))}，平均 {_fmt(statistics.fmean(nums))}，"
                        f"中位数 {_fmt(statistics.median(nums))}")
        elif kind.startswith("文本") and present:
            lens = [len(str(v)) for v in present]
            note = f"长度 最短 {min(lens)}，平均 {statistics.fmean(lens):.0f}，最长 {max(lens)} 字"
            dup_vals = len(hashed) - distinct
            if dup_vals and distinct > len(hashed) * 0.5:
                note += f"；重复值 {dup_vals} 个"
        elif kind.startswith("数组") and present:
            lens = [len(v) for v in present if isinstance(v, list)]
            if lens:
                note = f"元素个数 平均 {statistics.fmean(lens):.1f}，最多 {max(lens)}"
        lines.append(f"| {c} | {kind} | {len(present):,} | {empty:,} | {distinct:,} | {note} |")
        # 取值分布：类别型字段（不同值不多，或明显重复）
        if present and (distinct <= 50 or distinct <= len(present) * 0.3):
            top = Counter(hashed).most_common(TOP_N)
            share = "；".join(f"{v}：{n:,} 条（{n / len(present):.1%}）" for v, n in top)
            more = f"；其余 {distinct - len(top)} 个取值" if distinct > len(top) else ""
            details.append(f"- **{c}**（{distinct} 个取值）：{share}{more}")
        elif kind.startswith("文本") and distinct < len(hashed):  # 高基数文本里的重复项
            top = [(v, n) for v, n in Counter(hashed).most_common(5) if n > 1]
            if top:
                details.append(f"- **{c}** 出现多次的值：" + "；".join(f"「{_cell(v, 40)}」×{n}" for v, n in top))
    if details:
        lines += ["", "## 取值分布与重复", ""] + details
    k = min(15, len(rows))
    if k:
        idx = sorted({round(i * (len(rows) - 1) / max(1, k - 1)) for i in range(k)})
        show = cols[:8]
        lines += ["", f"## 样例记录（均匀抽取 {len(idx)} 条，记录序号从 1 开始）", "",
                  "| 序号 | " + " | ".join(show) + " |", "|---|" + "---|" * len(show)]
        for i in idx:
            lines.append(f"| {i + 1} | " + " | ".join(_cell(rows[i].get(c, "")) for c in show) + " |")
        if len(cols) > len(show):
            lines.append(f"\n（样例只显示前 {len(show)} 个字段）")
    return "\n".join(lines)


def records_section(records: list, limit_chars: int = 3_000_000) -> str:
    """全部记录，每条一行（紧凑 JSON），带序号，便于回答具体记录的问题。"""
    out = ["# 数据记录（每行一条）", ""]
    size = 0
    for i, r in enumerate(records, 1):
        line = f"〔第 {i} 条〕 " + json.dumps(r, ensure_ascii=False, separators=(",", ":"))
        size += len(line)
        if size > limit_chars:
            out.append(f"……（其余 {len(records) - i + 1:,} 条未展开，统计见“数据概览”）")
            break
        out.append(line)
    return "\n".join(out)


def table_rows_to_records(rows: list[list]) -> list[dict]:
    """表格（首行为表头）→ 记录列表。"""
    rows = [r for r in rows if any(c not in (None, "") for c in r)]
    if not rows:
        return []
    header = [str(h).strip() if h not in (None, "") else f"列{i + 1}" for i, h in enumerate(rows[0])]
    return [{header[i]: (r[i] if i < len(r) else None) for i in range(len(header))} for r in rows[1:]]
