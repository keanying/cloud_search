from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...contracts import TaskSpec


class ClarifyItem(BaseModel):
    """一个澄清问题及候选答案（界面上以选项展示，另有“其他”可自由输入）。"""

    question: str = Field(description="问题（简短，一句话）")
    options: list[str] = Field(default_factory=list, description="2-5 个最常见的候选答案，简短（≤12字）、互不重叠；"
                                                                 "不要包含“其他”（界面会自动提供）")
    multi: bool = Field(default=False, description="是否可多选（例如“感兴趣的方向”可多选；“地区”通常单选）")


class IntentDecision(BaseModel):
    """需求编译结果。chat=直接答复；clarify=需要用户补充；task=需要联网执行的任务。"""

    kind: Literal["chat", "clarify", "task"]
    reply: str = Field(description="给用户的回复。chat 时为完整回答；clarify/task 时为一两句说明")
    conversation_title: str | None = Field(default=None, description="对话标题（≤20字），首轮时给出")
    questions: list[str] = Field(default_factory=list, description="clarify 时需要用户回答的问题（≤4个）")
    clarify_items: list[ClarifyItem] = Field(default_factory=list,
                                             description="clarify 时与 questions 一一对应：每个问题附 2-5 个候选答案")
    task_spec: TaskSpec | None = Field(default=None, description="kind=task 时必填")
    needs_confirmation: bool = Field(default=False, description="范围/字段/费用需用户确认时为 true")
    plan_steps: list[str] = Field(default_factory=list, description="给用户看的简版计划（3-6步）")
