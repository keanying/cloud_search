from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChartSeries(BaseModel):
    name: str
    values: list[float | None]


class ChartSpec(BaseModel):
    """图表：数据必须逐个来自证据原文或计算结果（程序会核对，核对不上的图表会被删除）。"""

    id: str = Field(description="图表编号，如 c1；正文中用 [[chart:c1]] 放置")
    type: Literal["bar", "line", "pie"]
    title: str
    unit: str | None = None
    categories: list[str] = Field(min_length=1, max_length=20)
    series: list[ChartSeries] = Field(min_length=1, max_length=4)
    source: str | None = Field(default=None, description="数据来源说明，如 来源[1][3] 或 计算结果")


class Highlight(BaseModel):
    """关键数字卡片：数值必须原样出现在该来源的证据中（程序核对）。"""

    label: str = Field(description="指标名称（≤12字），如 2024年观众人次")
    value: str = Field(description="数值（原文写法，如 1,700 或 62%）")
    unit: str | None = Field(default=None, description="单位，如 万人次")
    source_n: int = Field(description="来源序号")


class TimelineItem(BaseModel):
    """时间轴节点：date 必须出现在 source_n 对应来源的证据里（程序核对年份/日期）。"""

    date: str = Field(description="原文中的年份或日期，如 1956、2017-06、2022年11月30日")
    title: str = Field(description="事件（≤20字）")
    detail: str | None = Field(default=None, description="一句补充（≤40字），可省略")
    source_n: int = Field(description="来源序号")


class SectionDraft(BaseModel):
    """报告的一章（分章撰写时使用）。"""

    heading: str = Field(description="章标题（不含“一、”这类编号），如“专家系统：1970年代至1980年代末”")
    markdown: str = Field(description="本章正文（不要再写章标题）：用 ### 小标题分 2-4 节，以段落为主，事实句末尾 [n]")
    charts: list[ChartSpec] = Field(default_factory=list, description="可选，本章最多 1 个图表；正文用 [[chart:编号]] 放置")


class ReportDraft(BaseModel):
    title: str
    summary: str = Field(default="", description="摘要：2-4 句，直接回答核心问题，带 [n] 引用")
    key_points: list[str] = Field(default_factory=list, description="要点：3-6 条，每条一句话，带 [n] 引用")
    markdown: str = Field(description="正文 Markdown（不要重复标题、摘要和要点），事实句末尾用 [n] 引用来源序号")
    charts: list[ChartSpec] = Field(default_factory=list, description="可选图表（≤3 个）")
    highlights: list[Highlight] = Field(default_factory=list, description="关键数字（≤4个，必须来自证据原文）")
    timeline: list[TimelineItem] = Field(default_factory=list,
                                         description="可选：发展历程/多个时间节点类主题的关键里程碑（≤12条，按时间排序）")
    limitations: list[str] = Field(default_factory=list, description="局限、缺口与不确定性")
    follow_ups: list[str] = Field(default_factory=list, description="用户接下来可能想问的 3 个问题（具体、可直接发送）")
