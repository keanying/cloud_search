from __future__ import annotations

from pydantic import BaseModel, Field


class QueryItem(BaseModel):
    query: str = Field(description="搜索引擎查询词，简洁，2-8个词")
    purpose: str = Field(description="这个查询要找什么")


class QueryPlan(BaseModel):
    queries: list[QueryItem] = Field(min_length=1)
