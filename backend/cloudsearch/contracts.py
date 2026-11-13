"""智能体之间共享的业务契约（TaskSpec 及流水线中间产物）。

TaskSpec 正式业务字段：mode、title、requirement_text、scope、dataset、report、output_formats、limits。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TaskMode = Literal["quick_search", "research", "dataset", "hybrid"]
FieldType = Literal["string", "number", "integer", "date", "url", "boolean"]

MODE_LABELS: dict[str, str] = {
    "quick_search": "搜索问题",
    "research": "深入研究",
    "dataset": "采集数据",
    "hybrid": "数据+报告",
}


class FieldSpec(BaseModel):
    key: str = Field(description="字段英文键，snake_case，如 museum_name")
    label: str = Field(description="字段中文名")
    type: FieldType = "string"
    required: bool = False
    description: str | None = None
    unit: str | None = None

    @field_validator("key")
    @classmethod
    def _snake(cls, v: str) -> str:
        v = re.sub(r"[^a-z0-9_]", "_", v.strip().lower()).strip("_") or "field"
        return v[:48] if not v[0].isdigit() else f"f_{v}"[:48]


class DatasetSpec(BaseModel):
    entity: str = Field(description="一行记录代表什么（记录粒度），如“一个博物馆的一条讲解资料”")
    fields: list[FieldSpec] = Field(min_length=1, max_length=30)
    max_records: int = Field(default=30, ge=1, le=500)
    analysis_request: str | None = Field(default=None, description="用户要求的统计/分析（可空）")


class ReportSpec(BaseModel):
    question: str
    audience: str | None = None
    outline: list[str] = Field(default_factory=list, description="建议提纲（可空，由写作智能体补全）")
    length: Literal["short", "medium", "long"] = "medium"


class Scope(BaseModel):
    questions: list[str] = Field(default_factory=list, description="需要回答的问题")
    topics: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list, description="用户点名的对象（可空，不是必填主档）")
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    time_range: str | None = None
    region: str | None = None
    language: str = "zh"


class Limits(BaseModel):
    max_queries: int = Field(default=5, ge=1, le=20)
    max_sources: int = Field(default=8, ge=1, le=40)
    max_llm_requests: int = Field(default=60, ge=5, le=500)


class TaskSpec(BaseModel):
    mode: TaskMode
    title: str = Field(max_length=120)
    requirement_text: str
    scope: Scope = Field(default_factory=Scope)
    dataset: DatasetSpec | None = None
    report: ReportSpec | None = None
    output_formats: list[Literal["md", "csv", "xlsx", "json"]] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)


# ---------------------------------------------------------------- 流水线中间产物
class SearchQuery(BaseModel):
    """一条搜索：查询词 + 用途 + 语言 + 时间范围（引擎支持时用于过滤）。"""

    query: str = Field(description="实际提交给搜索引擎的查询词，可含 site: \"精确短语\" -排除词 等语法")
    purpose: str = Field(default="", description="这条查询要找什么（对应哪个问题/字段）")
    language: Literal["zh", "en"] = Field(default="zh", description="结果语言/地区：zh 中文，en 英文")
    recency: Literal["day", "week", "month", "year"] | None = Field(
        default=None, description="只在用户明确要求最新/近期信息时填写")


class SearchHit(BaseModel):
    engine: str
    query: str
    rank: int
    url: str
    title: str | None = None
    snippet: str | None = None


class SourceDoc(BaseModel):
    """已实际读取的来源（正文另存对象存储；此处给智能体的是截断后的正文）。"""

    n: int = Field(description="来源序号，用于引用 [n]")
    source_revision_id: str
    url: str
    title: str | None = None
    site_name: str | None = None
    publish_time_text: str | None = None
    text: str


class Finding(BaseModel):
    """抽取出的单条事实及其原文摘录。"""

    claim: str = Field(description="用自己的话概括的一条事实（简洁）")
    quote: str = Field(description="支持该事实的原文摘录，必须逐字来自来源正文，20-200字")
    aspect: str | None = Field(default=None, description="对应的问题/子题/字段")


class RecordCandidate(BaseModel):
    """数据模式下抽取的一行候选记录。值必须有原文支撑，否则为 null 并给出缺失原因。"""

    entity_name: str = Field(description="该行对象的名称（用于去重）")
    values: dict[str, Any] = Field(description="字段键 → 值；无依据为 null")
    quotes: dict[str, str] = Field(default_factory=dict, description="字段键 → 逐字原文摘录")
    missing_reasons: dict[str, Literal["not_found", "not_disclosed", "not_applicable", "source_conflict"]] = Field(
        default_factory=dict)


class EvidenceRef(BaseModel):
    evidence_id: str
    n: int
    claim: str
    quote: str
    aspect: str | None = None
