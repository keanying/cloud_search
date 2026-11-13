"""确定性计算：把受限的 AnalysisPlan 编译为参数化 SQL，在内存 DuckDB 中执行。模型不心算。"""

from __future__ import annotations

from typing import Any

import duckdb

from ...contracts import FieldSpec
from .schemas import Analysis, AnalysisResult

NUMERIC = {"number", "integer"}


class InvalidAnalysis(ValueError):
    pass


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def run_analysis(records: list[dict[str, Any]], fields: list[FieldSpec], a: Analysis) -> AnalysisResult:
    types = {f.key: f.type for f in fields}
    keys = list(types)

    def need(field: str | None, numeric: bool = False) -> str:
        if field is None or field not in types:
            raise InvalidAnalysis(f"未知字段: {field}")
        if numeric and types[field] not in NUMERIC:
            raise InvalidAnalysis(f"字段 {field} 不是数值类型")
        return _q(field)

    con = duckdb.connect(":memory:")
    try:
        cols = ", ".join(f"{_q(k)} {'DOUBLE' if types[k] in NUMERIC else 'VARCHAR'}" for k in keys)
        con.execute(f"CREATE TABLE t ({cols})")
        warnings: list[str] = []
        rows = []
        for r in records:
            row = []
            for k in keys:
                v = r.get(k)
                if v is not None and types[k] in NUMERIC:
                    try:
                        v = float(str(v).replace(",", ""))
                    except ValueError:
                        warnings.append(f"字段 {k} 的值“{v}”无法转为数字，按空值处理")
                        v = None
                elif v is not None:
                    v = str(v)
                row.append(v)
            rows.append(row)
        if rows:
            con.executemany(f"INSERT INTO t VALUES ({', '.join('?' for _ in keys)})", rows)

        select, aliases = [], {}
        for g in a.group_by:
            select.append(need(g))
            aliases[g] = need(g)
        for m in a.metrics:
            if m.func == "count":
                expr = "COUNT(*)" if m.field is None else f"COUNT({need(m.field)})"
            elif m.func == "count_distinct":
                expr = f"COUNT(DISTINCT {need(m.field)})"
            else:
                expr = f"ROUND({m.func.upper()}({need(m.field, numeric=True)}), 4)"
            select.append(f"{expr} AS {_q(m.alias)}")
            aliases[m.alias] = _q(m.alias)

        where, params = [], []
        for f in a.filters:
            col = need(f.field)
            if f.op == "is_null":
                where.append(f"{col} IS NULL")
            elif f.op == "not_null":
                where.append(f"{col} IS NOT NULL")
            elif f.op == "contains":
                where.append(f"CAST({col} AS VARCHAR) LIKE ?")
                params.append(f"%{f.value}%")
            else:
                where.append(f"{col} {f.op} ?")
                params.append(f.value)
        sql = f"SELECT {', '.join(select)} FROM t"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if a.group_by:
            sql += " GROUP BY " + ", ".join(need(g) for g in a.group_by)
        if a.order_by:
            if a.order_by not in aliases:
                raise InvalidAnalysis(f"排序列不存在: {a.order_by}")
            sql += f" ORDER BY {aliases[a.order_by]} {'DESC' if a.descending else 'ASC'} NULLS LAST"
        sql += f" LIMIT {int(a.limit)}"
        cur = con.execute(sql, params)
        columns = [d[0] for d in cur.description]
        out_rows = [list(r) for r in cur.fetchall()]
        return AnalysisResult(title=a.title, description=a.description, columns=columns, rows=out_rows, sql=sql,
                              warnings=sorted(set(warnings))[:10])
    finally:
        con.close()
