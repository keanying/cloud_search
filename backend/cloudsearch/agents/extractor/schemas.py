from __future__ import annotations

from pydantic import BaseModel, Field

from ...contracts import Finding, RecordCandidate


class ExtractionOutput(BaseModel):
    relevant: bool = Field(description="该来源是否与任务相关")
    findings: list[Finding] = Field(default_factory=list, description="与问题相关的事实（≤12条）")
    records: list[RecordCandidate] = Field(default_factory=list, description="数据模式下的候选记录（≤20行）")
