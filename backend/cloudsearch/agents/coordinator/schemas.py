from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...contracts import SearchQuery


class AspectCoverage(BaseModel):
    question: str = Field(description="子问题（原文照抄）")
    status: Literal["covered", "partial", "missing"]
    note: str = Field(default="", description="还缺什么（≤30字）")


class CoverageReview(BaseModel):
    sufficient: bool = Field(description="现有证据是否已足以回答全部子问题/填充必填字段")
    aspects: list[AspectCoverage] = Field(default_factory=list, description="逐个子问题的覆盖情况")
    missing_aspects: list[str] = Field(default_factory=list, description="仍缺少的方面")
    extra_queries: list[SearchQuery] = Field(default_factory=list,
                                             description="针对缺口的补查（≤3条，purpose 写对应子问题，不重复已用查询）")
