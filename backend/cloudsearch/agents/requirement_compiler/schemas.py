from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...contracts import TaskSpec


class IntentDecision(BaseModel):
    """需求编译结果。chat=直接答复；clarify=需要用户补充；task=需要联网执行的任务。"""

    kind: Literal["chat", "clarify", "task"]
    reply: str = Field(description="给用户的回复。chat 时为完整回答；clarify/task 时为一两句说明")
    conversation_title: str | None = Field(default=None, description="对话标题（≤20字），首轮时给出")
    questions: list[str] = Field(default_factory=list, description="clarify 时需要用户回答的问题（≤4个）")
    task_spec: TaskSpec | None = Field(default=None, description="kind=task 时必填")
    needs_confirmation: bool = Field(default=False, description="范围/字段/费用需用户确认时为 true")
    plan_steps: list[str] = Field(default_factory=list, description="给用户看的简版计划（3-6步）")
