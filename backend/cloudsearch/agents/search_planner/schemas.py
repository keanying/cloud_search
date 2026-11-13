from __future__ import annotations

from pydantic import BaseModel, Field

from ...contracts import SearchQuery


class QueryPlan(BaseModel):
    """搜索计划：先理解意图，再给出查询词矩阵。"""

    intent: str = Field(description="用一两句话说明用户真正想要什么（目的、对象、隐含约束，如地区/时效/权威来源）")
    key_entities: list[str] = Field(default_factory=list, description="必须出现的核心对象/专有名词（用于精确匹配）")
    preferred_sources: list[str] = Field(default_factory=list,
                                         description="适合该需求的权威站点域名，如 dpm.org.cn、gov.cn；没有把握就留空")
    queries: list[SearchQuery] = Field(min_length=1)


class SelectedCandidate(BaseModel):
    index: int = Field(description="候选编号")
    reason: str = Field(default="", description="为什么值得读（≤20字）")


class CandidateSelection(BaseModel):
    selected: list[SelectedCandidate] = Field(description="按阅读优先级从高到低排列")


class QueryRefinement(BaseModel):
    queries: list[SearchQuery] = Field(default_factory=list, description="改写后的查询；没有更好的写法就返回空")


# 兼容旧名称
QueryItem = SearchQuery
