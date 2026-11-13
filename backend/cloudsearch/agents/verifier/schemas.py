from __future__ import annotations

from pydantic import BaseModel, Field


class Conflict(BaseModel):
    evidence_nos: list[int] = Field(description="相互矛盾的证据编号")
    description: str


class ConflictReport(BaseModel):
    conflicts: list[Conflict] = Field(default_factory=list)
    unsupported: list[int] = Field(default_factory=list, description="摘录并不支持其 claim 的证据编号")
    notes: str | None = None
