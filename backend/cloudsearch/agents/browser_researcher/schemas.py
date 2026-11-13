from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ElementRef(BaseModel):
    element_id: str
    kind: str
    text: str


class Observation(BaseModel):
    """一次页面观察：只暴露签发的元素引用，模型不能提交 CSS/XPath/脚本。"""

    observation_id: str
    url: str
    title: str
    text_excerpt: str
    elements: list[ElementRef]


class BrowserAction(BaseModel):
    action: Literal["click", "scroll", "finish"] = Field(
        description="click=点击一个签发的元素；scroll=向下滚动加载更多；finish=结束交互")
    element_id: str | None = Field(default=None, description="click 时必填，必须来自当前观察的 elements")
    reason: str = Field(description="简短理由")
