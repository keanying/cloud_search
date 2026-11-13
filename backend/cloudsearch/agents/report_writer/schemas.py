from __future__ import annotations

from pydantic import BaseModel, Field


class ReportDraft(BaseModel):
    title: str
    markdown: str = Field(description="Markdown 正文，事实句末尾用 [n] 引用来源序号")
    limitations: list[str] = Field(default_factory=list, description="局限、缺口与不确定性")
