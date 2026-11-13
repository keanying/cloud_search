"""对外 API 契约（/api/v1）。前端类型以此为准。

消息 parts（MessageOut.parts 中每一项都含 type 与 part_id）：
- text:          {type, part_id, text, citations?: [{n, source_revision_id, url, title}]}
                 正文中的 [n] 对应 citations[n]
- clarification: {type, part_id, questions: [str]}
- plan_summary:  {type, part_id, task_id, mode, title, summary, steps: [str], limits: {max_queries, max_sources},
                  fields?: [{key, label, type, required}], plan_hash, status: awaiting_confirmation|confirmed|auto_started}
- progress:      {type, part_id, task_id, task_status, stage, stage_label,
                  stages: [{key, label, status: pending|running|done|skipped|failed}],
                  counters: {queries, candidates, sources_read, sources_failed, evidence}, browser_available: bool}
- source:        {type, part_id, task_id, sources: [{n, source_revision_id, title, url, site_name, retrieved_time}]}
- artifact:      {type, part_id, task_id, artifact_id, artifact_kind, display_name, mime_name, byte_qty,
                  record_qty, content_hash, quality_status}
- error:         {type, part_id, code, message, task_id?}

SSE（GET /conversations/{id}/events）：每条 `id: <event_seq_no>`，`event: <event_type>`，`data: <json>`
- message_created / message_updated: data = MessageOut
- task_updated: data = TaskOut
- conversation_updated: data = ConversationOut
- heartbeat：注释行，不占序号
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ModeSelection = Literal["auto", "quick_search", "research", "dataset", "hybrid"]
TaskMode = Literal["quick_search", "research", "dataset", "hybrid"]


# ---------------------------------------------------------------- 认证
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    is_admin: bool
    project_id: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------------------------------------------------------- 会话与消息
class ConversationIn(BaseModel):
    title: str | None = None


class ConversationPatch(BaseModel):
    title: str | None = None
    conversation_status: Literal["active", "archived"] | None = None


class ConversationOut(BaseModel):
    conversation_id: str
    title: str
    conversation_status: str
    last_event_seq_no: int
    active_task_qty: int = 0
    created_time: datetime
    updated_time: datetime


class ConversationList(BaseModel):
    items: list[ConversationOut]
    next_cursor: str | None = None


class MessageIn(BaseModel):
    client_message_id: str = Field(min_length=8, max_length=64, description="客户端生成的幂等ID（UUID）")
    text: str = Field(min_length=1, max_length=20000)
    mode_selection: ModeSelection = "auto"


class MessageOut(BaseModel):
    message_id: str
    conversation_id: str
    turn_id: str
    role: Literal["user", "assistant"]
    parts: list[dict[str, Any]]
    message_status: str
    mode_selection: str | None = None
    task_ids: list[str] = []
    created_time: datetime
    updated_time: datetime


class MessageList(BaseModel):
    items: list[MessageOut]
    last_event_seq_no: int


class SendMessageOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    deduplicated: bool = False


# ---------------------------------------------------------------- 任务
class TaskOut(BaseModel):
    task_id: str
    conversation_id: str | None
    parent_task_id: str | None
    mode: str
    title: str
    task_status: str
    status_reason: str | None
    current_stage: str | None
    cancel_generation: int
    plan_hash: str | None
    task_spec: dict[str, Any]
    result_summary: dict[str, Any] | None
    error_code: str | None
    error_desc: str | None
    llm_request_qty: int
    spent_minor_amt: int
    cost_unknown_qty: int
    created_time: datetime
    updated_time: datetime


class ConfirmIn(BaseModel):
    plan_hash: str


class StopTurnIn(BaseModel):
    turn_id: str | None = Field(default=None, description="缺省为最近一轮")


class TaskControlResult(BaseModel):
    task_id: str
    outcome: Literal["accepted", "not_needed", "conflict", "forbidden"]
    task_status: str | None = None


class StopTurnOut(BaseModel):
    turn_id: str | None
    results: list[TaskControlResult]


class EvidenceOut(BaseModel):
    evidence_id: str
    quote_text: str
    claim_text: str | None
    verification_status: str


class SourceOut(BaseModel):
    n: int
    source_revision_id: str
    title: str | None
    request_url: str
    final_url: str | None
    site_name: str | None
    author: str | None
    publish_time_text: str | None
    retrieved_time: datetime
    access_method: str
    revision_status: str
    failure_reason: str | None
    evidence: list[EvidenceOut] = []


class CandidateOut(BaseModel):
    candidate_id: str
    query_text: str
    engine_name: str
    rank_no: int
    url: str
    title: str | None
    snippet: str | None
    candidate_status: str


class TaskSourcesOut(BaseModel):
    sources: list[SourceOut]
    candidates: list[CandidateOut]


# ---------------------------------------------------------------- 浏览器阅览（只读）
class BrowserSessionOut(BaseModel):
    browser_session_id: str
    task_id: str
    session_label: str
    session_status: str
    current_url: str | None
    current_title: str | None
    current_activity: str | None
    frame_seq_no: int
    frame_time: datetime | None


class ViewerMetaOut(BrowserSessionOut):
    preview_mode: Literal["snapshot"] = "snapshot"
    connected: bool
    stale: bool
    masked: bool
    task_status: str | None


# ---------------------------------------------------------------- 产物
class ArtifactOut(BaseModel):
    artifact_id: str
    task_id: str | None
    conversation_id: str | None = None
    artifact_kind: str
    display_name: str
    mime_name: str
    byte_qty: int
    record_qty: int | None
    content_hash: str
    quality_status: str
    artifact_status: str
    created_time: datetime


class ArtifactPreviewOut(BaseModel):
    kind: Literal["table", "markdown", "text"]
    content: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    total_rows: int | None = None
    shown_rows: int | None = None


# ---------------------------------------------------------------- 大模型管理（管理员）
class ProviderPreset(BaseModel):
    provider_type: str
    provider_name: str
    base_url: str
    example_models: list[str]
    note: str | None = None


class ProviderIn(BaseModel):
    provider_name: str
    provider_type: str
    base_url: str
    api_key: str | None = Field(default=None, description="仅写入；读取时只返回掩码")
    enabled: bool = True


class ProviderPatch(BaseModel):
    provider_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None


class ProviderOut(BaseModel):
    provider_id: str
    provider_name: str
    provider_type: str
    base_url: str
    has_api_key: bool
    api_key_mask: str | None
    enabled: bool


class ModelIn(BaseModel):
    provider_id: str
    model_name: str
    display_name: str | None = None
    supports_tools: bool = True
    supports_json_schema: bool = False
    supports_json_object: bool = True
    supports_vision: bool = False
    context_window_qty: int | None = None
    max_output_qty: int | None = None
    input_price_minor_amt: int | None = Field(default=None, description="每百万输入token价格，单位：分")
    output_price_minor_amt: int | None = None
    currency_code: str = "CNY"
    enabled: bool = True


class ModelPatch(BaseModel):
    display_name: str | None = None
    supports_tools: bool | None = None
    supports_json_schema: bool | None = None
    supports_json_object: bool | None = None
    supports_vision: bool | None = None
    context_window_qty: int | None = None
    max_output_qty: int | None = None
    input_price_minor_amt: int | None = None
    output_price_minor_amt: int | None = None
    currency_code: str | None = None
    enabled: bool | None = None


class ModelOut(ModelIn):
    model_profile_id: str
    provider_name: str | None = None


class ModelTestOut(BaseModel):
    ok: bool
    latency_ms: int | None = None
    reply: str | None = None
    error: str | None = None


class AgentBindingIn(BaseModel):
    model_profile_id: str
    fallback_profile_ids: list[str] = []
    temperature: float | None = None
    max_tokens: int | None = None


class AgentBindingOut(BaseModel):
    agent_role: str
    role_label: str
    description: str
    model_profile_id: str | None
    fallback_profile_ids: list[str]
    temperature: float | None
    max_tokens: int | None
