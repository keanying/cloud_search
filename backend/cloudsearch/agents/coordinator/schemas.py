from __future__ import annotations

from pydantic import BaseModel, Field


class CoverageReview(BaseModel):
    sufficient: bool = Field(description="现有证据是否已足以回答全部必答问题/填充必填字段")
    missing_aspects: list[str] = Field(default_factory=list, description="仍缺少的方面")
    extra_queries: list[str] = Field(default_factory=list, description="补查搜索词（≤3个，不重复已用查询）")
