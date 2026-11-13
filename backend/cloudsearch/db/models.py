"""cloudsearch_app 应用状态表（P0 核心子集）。

命名遵循设计文档：src_opr_*_f（运行/控制）与 src_prd_*_f（产出）；全部非分区；
ID 为不透明字符串；时间为 UTC DATETIME(3)；未知值为 NULL，不用 0 或读取日代填。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from ..core.ids import utcnow
from .base import Base

ID = String(64)
ENUM = String(32)
DT = DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")
BIGINT = BigInteger().with_variant(Integer(), "sqlite")  # SQLite 自增需 INTEGER


def _now() -> datetime:
    return utcnow()


class TimestampMixin:
    created_time: Mapped[datetime] = mapped_column(DT, default=_now, comment="创建时间UTC")
    updated_time: Mapped[datetime] = mapped_column(DT, default=_now, onupdate=_now, comment="更新时间UTC")


# ---------------------------------------------------------------- 用户、项目、授权
class User(Base, TimestampMixin):
    __tablename__ = "src_opr_user_f"
    __table_args__ = {"comment": "用户"}
    user_id: Mapped[str] = mapped_column(ID, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, comment="登录名")
    password_hash: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(64))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, comment="平台管理员")
    user_status: Mapped[str] = mapped_column(ENUM, default="active")


class Project(Base, TimestampMixin):
    __tablename__ = "src_opr_project_f"
    __table_args__ = {"comment": "项目（隔离范围）"}
    project_id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_name: Mapped[str] = mapped_column(String(128))
    owner_user_id: Mapped[str] = mapped_column(ID)


class ProjectMember(Base, TimestampMixin):
    __tablename__ = "src_opr_project_member_f"
    __table_args__ = {"comment": "项目成员；role_type: admin/operator/reviewer/data_engineer/reader"}
    project_id: Mapped[str] = mapped_column(ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ID, primary_key=True)
    role_type: Mapped[str] = mapped_column(ENUM, default="operator")
    member_status: Mapped[str] = mapped_column(ENUM, default="active")


# ---------------------------------------------------------------- 大模型配置
class LlmProvider(Base, TimestampMixin):
    __tablename__ = "src_opr_llm_provider_f"
    __table_args__ = {"comment": "大模型供应方（OpenAI兼容接口）；api_key 仅加密存储"}
    provider_id: Mapped[str] = mapped_column(ID, primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(64), comment="显示名，如 DeepSeek")
    provider_type: Mapped[str] = mapped_column(ENUM, comment="openai/deepseek/moonshot/volcengine/dashscope/zhipu/openai_compatible")
    base_url: Mapped[str] = mapped_column(String(512))
    api_key_cipher: Mapped[str | None] = mapped_column(Text, comment="Fernet 密文")
    api_key_mask: Mapped[str | None] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class LlmModel(Base, TimestampMixin):
    __tablename__ = "src_opr_llm_model_f"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uk_llm_model"),
        {"comment": "模型配置与能力矩阵；单价为每百万token最小货币单位，未知为NULL"},
    )
    model_profile_id: Mapped[str] = mapped_column(ID, primary_key=True)
    provider_id: Mapped[str] = mapped_column(ID, index=True)
    model_name: Mapped[str] = mapped_column(String(128), comment="供应方模型名，如 deepseek-chat / 豆包接入点ID")
    display_name: Mapped[str | None] = mapped_column(String(128))
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_forced_tool_choice: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(),
        comment="是否接受强制工具调用(tool_choice=required)；思考模式模型常不支持，运行中会自动探测并回写")
    supports_json_schema: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_json_object: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    context_window_qty: Mapped[int | None] = mapped_column(Integer)
    max_output_qty: Mapped[int | None] = mapped_column(Integer)
    input_price_minor_amt: Mapped[int | None] = mapped_column(BIGINT, comment="每百万输入token价格（分）")
    output_price_minor_amt: Mapped[int | None] = mapped_column(BIGINT, comment="每百万输出token价格（分）")
    currency_code: Mapped[str] = mapped_column(String(8), default="CNY")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentModelBinding(Base, TimestampMixin):
    __tablename__ = "src_opr_agent_model_binding_f"
    __table_args__ = {"comment": "智能体角色与模型绑定（含备用模型链）"}
    agent_role: Mapped[str] = mapped_column(ENUM, primary_key=True)
    model_profile_id: Mapped[str] = mapped_column(ID)
    fallback_profile_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    temperature: Mapped[float | None] = mapped_column()
    max_tokens: Mapped[int | None] = mapped_column(Integer)


# ---------------------------------------------------------------- 会话与消息
class Conversation(Base, TimestampMixin):
    __tablename__ = "src_opr_conversation_f"
    __table_args__ = (Index("ix_conv_user", "project_id", "user_id", "updated_time"), {"comment": "对话"})
    conversation_id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID)
    user_id: Mapped[str] = mapped_column(ID)
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    conversation_status: Mapped[str] = mapped_column(ENUM, default="active", comment="active/archived/deleted")
    last_event_seq_no: Mapped[int] = mapped_column(BIGINT, default=0, comment="会话事件水位")
    lock_version_no: Mapped[int] = mapped_column(Integer, default=1)


class Message(Base, TimestampMixin):
    __tablename__ = "src_opr_message_f"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_message_id", name="uk_msg_client"),
        Index("ix_msg_conv", "conversation_id", "created_time"),
        {"comment": "消息；parts 为 text/clarification/plan_summary/progress/source/artifact/approval/error"},
    )
    message_id: Mapped[str] = mapped_column(ID, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ID)
    project_id: Mapped[str] = mapped_column(ID)
    turn_id: Mapped[str] = mapped_column(ID, comment="用户提交及其回复的逻辑轮次")
    role: Mapped[str] = mapped_column(ENUM, comment="user/assistant")
    client_message_id: Mapped[str | None] = mapped_column(String(64), comment="客户端幂等ID")
    request_hash: Mapped[str | None] = mapped_column(String(64))
    mode_selection: Mapped[str | None] = mapped_column(ENUM, comment="auto/quick_search/research/dataset/hybrid")
    parts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    message_status: Mapped[str] = mapped_column(ENUM, default="final", comment="pending/processing/final/error")
    revision_no: Mapped[int] = mapped_column(Integer, default=1)
    worker_id: Mapped[str | None] = mapped_column(String(64), comment="处理该轮回复的 worker")
    lease_expire_time: Mapped[datetime | None] = mapped_column(DT)


class ConversationEvent(Base):
    __tablename__ = "src_opr_conversation_event_f"
    __table_args__ = {"comment": "会话事件流（SSE 按 event_seq_no 补齐）"}
    conversation_id: Mapped[str] = mapped_column(ID, primary_key=True)
    event_seq_no: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=False)
    event_type: Mapped[str] = mapped_column(String(48))
    event_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    server_time: Mapped[datetime] = mapped_column(DT, default=_now)


# ---------------------------------------------------------------- 任务与执行
class Task(Base, TimestampMixin):
    __tablename__ = "src_opr_task_f"
    __table_args__ = (
        Index("ix_task_queue", "task_status", "created_time"),
        Index("ix_task_conv", "conversation_id"),
        {"comment": "根执行任务；状态 draft/ready/queued/running/pausing/paused/stopping/stopped/"
                    "completed/partial_failed/failed/cancelled"},
    )
    task_id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID)
    created_by_id: Mapped[str] = mapped_column(ID)
    conversation_id: Mapped[str | None] = mapped_column(ID, comment="发起会话（多对多另见关联表）")
    parent_task_id: Mapped[str | None] = mapped_column(ID)
    mode: Mapped[str] = mapped_column(ENUM, comment="quick_search/research/dataset/hybrid")
    title: Mapped[str] = mapped_column(String(200))
    task_spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    plan_hash: Mapped[str | None] = mapped_column(String(64))
    task_status: Mapped[str] = mapped_column(ENUM, default="draft")
    status_reason: Mapped[str | None] = mapped_column(String(64), comment="draft 时的 clarification/approval 等原因")
    cancel_generation: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(48))
    budget_limit_minor_amt: Mapped[int | None] = mapped_column(BIGINT)
    spent_minor_amt: Mapped[int] = mapped_column(BIGINT, default=0)
    cost_unknown_qty: Mapped[int] = mapped_column(Integer, default=0, comment="单价未知的调用次数")
    llm_request_qty: Mapped[int] = mapped_column(Integer, default=0)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_desc: Mapped[str | None] = mapped_column(Text)
    lock_version_no: Mapped[int] = mapped_column(Integer, default=1)


class MessageTaskRel(Base):
    __tablename__ = "src_opr_message_task_rel_f"
    __table_args__ = (
        Index("ix_mtr_task", "task_id"),
        Index("ix_mtr_turn", "conversation_id", "turn_id"),
        {"comment": "消息—任务绑定（request/progress/output）"},
    )
    message_id: Mapped[str] = mapped_column(ID, primary_key=True)
    task_id: Mapped[str] = mapped_column(ID, primary_key=True)
    binding_type: Mapped[str] = mapped_column(ENUM, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ID)
    turn_id: Mapped[str] = mapped_column(ID)
    created_time: Mapped[datetime] = mapped_column(DT, default=_now)


class TaskRun(Base, TimestampMixin):
    __tablename__ = "src_opr_task_run_f"
    __table_args__ = (
        UniqueConstraint("task_id", "run_seq_no", name="uk_run_seq"),
        Index("ix_run_claim", "run_status", "lease_expire_time"),
        {"comment": "一次运行；暂停恢复=同task新run；租约+epoch防止旧worker污染"},
    )
    run_id: Mapped[str] = mapped_column(ID, primary_key=True)
    task_id: Mapped[str] = mapped_column(ID)
    project_id: Mapped[str] = mapped_column(ID)
    run_seq_no: Mapped[int] = mapped_column(Integer)
    run_status: Mapped[str] = mapped_column(ENUM, default="queued")
    cancel_generation: Mapped[int] = mapped_column(Integer, default=0)
    plan_hash: Mapped[str | None] = mapped_column(String(64))
    resume_from_run_id: Mapped[str | None] = mapped_column(ID)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    lease_epoch: Mapped[int] = mapped_column(Integer, default=0)
    lease_expire_time: Mapped[datetime | None] = mapped_column(DT)
    started_time: Mapped[datetime | None] = mapped_column(DT)
    finished_time: Mapped[datetime | None] = mapped_column(DT)


class TaskStep(Base, TimestampMixin):
    __tablename__ = "src_opr_task_step_f"
    __table_args__ = (
        UniqueConstraint("task_id", "node_id", "cancel_generation", "attempt_no", name="uk_step_attempt"),
        Index("ix_step_task", "task_id", "step_status"),
        {"comment": "DAG节点执行；状态 queued/running/succeeded/no_content/blocked/retry_wait/failed/cancelled"},
    )
    step_id: Mapped[str] = mapped_column(ID, primary_key=True)
    task_id: Mapped[str] = mapped_column(ID)
    run_id: Mapped[str] = mapped_column(ID)
    node_id: Mapped[str] = mapped_column(String(128), comment="稳定节点ID，恢复时据此复用已完成产物")
    node_kind: Mapped[str] = mapped_column(ENUM, comment="agent/deterministic/browser/gate")
    agent_role: Mapped[str | None] = mapped_column(ENUM)
    step_status: Mapped[str] = mapped_column(ENUM, default="queued")
    cancel_generation: Mapped[int] = mapped_column(Integer, default=0)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    lease_epoch: Mapped[int] = mapped_column(Integer, default=0)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_desc: Mapped[str | None] = mapped_column(Text)
    started_time: Mapped[datetime | None] = mapped_column(DT)
    finished_time: Mapped[datetime | None] = mapped_column(DT)


class TaskEvent(Base):
    __tablename__ = "src_opr_task_event_f"
    __table_args__ = {"comment": "任务事件（审计）"}
    task_id: Mapped[str] = mapped_column(ID, primary_key=True)
    event_seq_no: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=False)
    event_type: Mapped[str] = mapped_column(String(48))
    event_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    server_time: Mapped[datetime] = mapped_column(DT, default=_now)


class AgentRun(Base):
    __tablename__ = "src_opr_agent_run_f"
    __table_args__ = (Index("ix_agent_run_task", "task_id"), {"comment": "智能体模型调用记录与费用"})
    agent_run_id: Mapped[str] = mapped_column(ID, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(ID)
    step_id: Mapped[str | None] = mapped_column(ID)
    conversation_id: Mapped[str | None] = mapped_column(ID)
    agent_role: Mapped[str] = mapped_column(ENUM)
    model_profile_id: Mapped[str | None] = mapped_column(ID)
    provider_name: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(String(128))
    request_qty: Mapped[int] = mapped_column(Integer, default=0)
    input_token_qty: Mapped[int] = mapped_column(Integer, default=0)
    output_token_qty: Mapped[int] = mapped_column(Integer, default=0)
    cost_minor_amt: Mapped[int | None] = mapped_column(BIGINT, comment="未知单价为NULL")
    currency_code: Mapped[str | None] = mapped_column(String(8))
    cost_status: Mapped[str] = mapped_column(ENUM, default="confirmed", comment="confirmed/unknown")
    run_status: Mapped[str] = mapped_column(ENUM, default="succeeded")
    error_desc: Mapped[str | None] = mapped_column(Text)
    started_time: Mapped[datetime] = mapped_column(DT, default=_now)
    finished_time: Mapped[datetime | None] = mapped_column(DT)


# ---------------------------------------------------------------- 云端浏览器与阅览
class BrowserSession(Base, TimestampMixin):
    __tablename__ = "src_opr_browser_session_f"
    __table_args__ = (Index("ix_bs_task", "task_id"), {"comment": "真实云端 BrowserContext 索引；阅览只读订阅"})
    browser_session_id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID)
    task_id: Mapped[str] = mapped_column(ID)
    run_id: Mapped[str] = mapped_column(ID)
    worker_id: Mapped[str] = mapped_column(String(64))
    session_label: Mapped[str] = mapped_column(String(64))
    session_status: Mapped[str] = mapped_column(ENUM, default="active", comment="creating/active/closing/closed/lost")
    current_url: Mapped[str | None] = mapped_column(String(2048))
    current_title: Mapped[str | None] = mapped_column(String(512))
    current_activity: Mapped[str | None] = mapped_column(String(128))
    frame_seq_no: Mapped[int] = mapped_column(Integer, default=0)
    frame_ref: Mapped[str | None] = mapped_column(String(512))
    frame_time: Mapped[datetime | None] = mapped_column(DT)
    frame_masked: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_time: Mapped[datetime | None] = mapped_column(DT)
    # 人工接管：none/requested/active/resolved/timeout/skipped
    handoff_state: Mapped[str] = mapped_column(ENUM, default="none", server_default="none")
    handoff_reason: Mapped[str | None] = mapped_column(String(256))
    handoff_deadline: Mapped[datetime | None] = mapped_column(DT)
    handoff_user_id: Mapped[str | None] = mapped_column(ID, comment="当前操作的用户（active 时）")
    live_endpoint: Mapped[str | None] = mapped_column(String(256), comment="所在 worker 的内部实时通道地址（多进程时由 API 转发）")


# ---------------------------------------------------------------- 来源与证据
class SourceCandidate(Base):
    __tablename__ = "src_opr_source_candidate_f"
    __table_args__ = (
        UniqueConstraint("task_id", "url_hash", name="uk_cand_url"),
        {"comment": "搜索候选（摘要只是线索，不是证据）"},
    )
    candidate_id: Mapped[str] = mapped_column(ID, primary_key=True)
    task_id: Mapped[str] = mapped_column(ID)
    query_text: Mapped[str] = mapped_column(String(512))
    engine_name: Mapped[str] = mapped_column(ENUM)
    rank_no: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(2048))
    url_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(512))
    snippet: Mapped[str | None] = mapped_column(Text)
    candidate_status: Mapped[str] = mapped_column(ENUM, default="discovered", comment="discovered/accepted/rejected/blocked")
    created_time: Mapped[datetime] = mapped_column(DT, default=_now)


class SourceRevision(Base):
    __tablename__ = "src_opr_source_revision_f"
    __table_args__ = (Index("ix_srcrev_task", "task_id"), {"comment": "实际读取的来源修订（不可变）"})
    source_revision_id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID)
    task_id: Mapped[str] = mapped_column(ID)
    candidate_id: Mapped[str | None] = mapped_column(ID)
    source_no: Mapped[int | None] = mapped_column(Integer, comment="任务内来源序号，对应引用 [n]")
    request_url: Mapped[str] = mapped_column(String(2048))
    final_url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(512))
    site_name: Mapped[str | None] = mapped_column(String(256), comment="发布主体/站点；未知为NULL")
    author: Mapped[str | None] = mapped_column(String(256))
    publish_time_text: Mapped[str | None] = mapped_column(String(64), comment="页面声明的发布时间原文；未知为NULL")
    retrieved_time: Mapped[datetime] = mapped_column(DT, default=_now)
    access_method: Mapped[str] = mapped_column(ENUM, comment="browser/http/user_file")
    browser_session_id: Mapped[str | None] = mapped_column(ID)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    content_ref: Mapped[str | None] = mapped_column(String(512))
    text_char_qty: Mapped[int] = mapped_column(Integer, default=0)
    revision_status: Mapped[str] = mapped_column(ENUM, comment="captured/no_content/blocked/failed")
    failure_reason: Mapped[str | None] = mapped_column(String(256))


class Evidence(Base):
    __tablename__ = "src_opr_evidence_f"
    __table_args__ = (Index("ix_evd_task", "task_id"), {"comment": "证据跨度：原文摘录必须是来源正文的子串"})
    evidence_id: Mapped[str] = mapped_column(ID, primary_key=True)
    task_id: Mapped[str] = mapped_column(ID)
    source_revision_id: Mapped[str] = mapped_column(ID)
    quote_text: Mapped[str] = mapped_column(Text)
    char_start_no: Mapped[int | None] = mapped_column(Integer)
    char_end_no: Mapped[int | None] = mapped_column(Integer)
    claim_text: Mapped[str | None] = mapped_column(Text, comment="抽取出的主张/字段值描述")
    verification_status: Mapped[str] = mapped_column(ENUM, default="candidate",
                                                     comment="candidate/machine_checked/conflicted/rejected")
    created_time: Mapped[datetime] = mapped_column(DT, default=_now)


# ---------------------------------------------------------------- 产物
class Artifact(Base):
    __tablename__ = "src_opr_artifact_f"
    __table_args__ = (Index("ix_art_task", "task_id"), {"comment": "文件产物（hash固定，修订新增不覆盖）"})
    artifact_id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID)
    task_id: Mapped[str | None] = mapped_column(ID)
    artifact_kind: Mapped[str] = mapped_column(ENUM, comment="answer/report/dataset/data_dictionary/sources")
    display_name: Mapped[str] = mapped_column(String(256))
    mime_name: Mapped[str] = mapped_column(String(128))
    storage_ref: Mapped[str] = mapped_column(String(512))
    byte_qty: Mapped[int] = mapped_column(BIGINT)
    content_hash: Mapped[str] = mapped_column(String(64))
    record_qty: Mapped[int | None] = mapped_column(Integer)
    quality_status: Mapped[str] = mapped_column(ENUM, default="machine_checked")
    artifact_status: Mapped[str] = mapped_column(ENUM, default="available")
    created_time: Mapped[datetime] = mapped_column(DT, default=_now)

