from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Metric(BaseModel):
    func: Literal["count", "count_distinct", "sum", "avg", "min", "max"]
    field: str | None = Field(default=None, description="count 可为空（计行数）")
    alias: str = Field(description="结果列名（中文可）")


class Filter(BaseModel):
    field: str
    op: Literal["=", "!=", ">", ">=", "<", "<=", "contains", "is_null", "not_null"]
    value: str | float | None = None


class Analysis(BaseModel):
    title: str
    description: str
    group_by: list[str] = Field(default_factory=list)
    metrics: list[Metric] = Field(min_length=1)
    filters: list[Filter] = Field(default_factory=list)
    order_by: str | None = Field(default=None, description="按某个 alias 或 group_by 字段排序")
    descending: bool = True
    limit: int = Field(default=20, ge=1, le=200)


class AnalysisPlan(BaseModel):
    analyses: list[Analysis] = Field(default_factory=list, max_length=5)


class AnalysisResult(BaseModel):
    title: str
    description: str
    columns: list[str]
    rows: list[list[Any]]
    sql: str
    warnings: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        if not self.rows:
            return f"**{self.title}**：无数据"
        head = "| " + " | ".join(self.columns) + " |\n|" + "---|" * len(self.columns)
        body = "\n".join("| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in self.rows)
        return f"**{self.title}**（{self.description}）\n\n{head}\n{body}"
