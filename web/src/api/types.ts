// 与 backend/cloudsearch/api/schemas.py 对应的前端类型。时间字段为 ISO 字符串。

export type ModeSelection = 'auto' | 'quick_search' | 'research' | 'dataset' | 'hybrid'
export type TaskMode = Exclude<ModeSelection, 'auto'>

export type TaskStatus =
  | 'draft'
  | 'ready'
  | 'queued'
  | 'running'
  | 'pausing'
  | 'paused'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'partial_failed'
  | 'failed'
  | 'cancelled'

// ---------------------------------------------------------------- 认证
export interface UserOut {
  user_id: string
  username: string
  display_name: string | null
  is_admin: boolean
  project_id: string
}

export interface TokenOut {
  access_token: string
  token_type: string
  user: UserOut
}

// ---------------------------------------------------------------- 会话与消息
export interface ConversationOut {
  conversation_id: string
  title: string
  conversation_status: string
  last_event_seq_no: number
  active_task_qty: number
  created_time: string
  updated_time: string
}

export interface ConversationList {
  items: ConversationOut[]
  next_cursor: string | null
}

export type Credibility = 'official' | 'academic' | 'media' | 'reference' | 'community' | 'aggregate' | 'unknown'

export interface Citation {
  n: number
  source_revision_id: string
  url: string
  title: string | null
  site_name?: string | null
  publish_time_text?: string | null
  credibility?: Credibility
  credibility_label?: string
  /** 该来源最有代表性的原文摘录（悬停预览） */
  quote?: string
}

export interface TextPart {
  type: 'text'
  part_id: string
  text: string
  citations?: Citation[]
}

export interface ClarificationPart {
  type: 'clarification'
  part_id: string
  questions: string[]
}

export interface PlanField {
  key: string
  label: string
  type: string
  required: boolean
}

export interface PlanSummaryPart {
  type: 'plan_summary'
  part_id: string
  task_id: string
  mode: TaskMode
  title: string
  summary: string
  steps: string[]
  limits: { max_queries?: number; max_sources?: number }
  fields?: PlanField[]
  plan_hash: string
  status: 'awaiting_confirmation' | 'confirmed' | 'auto_started'
}

export type StageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'

export interface ProgressPart {
  type: 'progress'
  part_id: string
  task_id: string
  task_status: TaskStatus
  stage: string | null
  stage_label: string | null
  stages: { key: string; label: string; status: StageStatus }[]
  counters: {
    queries?: number
    candidates?: number
    sources_read?: number
    sources_failed?: number
    evidence?: number
  }
  browser_available: boolean
}

export interface SourceBrief {
  n: number
  source_revision_id: string
  title: string | null
  url: string
  site_name: string | null
  retrieved_time: string | null
  publish_time_text?: string | null
  credibility?: Credibility
  credibility_label?: string
}

/** 关键数字：数值已由程序核对出现在对应来源的证据中 */
export interface HighlightItem {
  label: string
  value: string
  unit?: string | null
  source_n: number
  url?: string | null
}

export interface HighlightsPart {
  type: 'highlights'
  part_id: string
  items: HighlightItem[]
}

/** 接着问：基于本次结果的延伸问题 */
export interface SuggestionsPart {
  type: 'suggestions'
  part_id: string
  items: string[]
}

export interface SourcePart {
  type: 'source'
  part_id: string
  task_id: string
  sources: SourceBrief[]
}

export type ArtifactFormatName = 'docx' | 'pdf' | 'html' | 'md' | 'csv' | 'xlsx' | 'json'

/** 同一成果的不同文件格式（part 自身的 artifact_id 为主格式） */
export interface ArtifactFormat {
  format: ArtifactFormatName
  artifact_id: string
  byte_qty: number
}

export interface ArtifactPart {
  type: 'artifact'
  part_id: string
  task_id: string
  artifact_id: string
  artifact_kind: string
  display_name: string
  mime_name: string
  byte_qty: number
  record_qty: number | null
  content_hash: string
  quality_status: string
  formats?: ArtifactFormat[]
}

export type HandoffState = 'none' | 'requested' | 'active' | 'resolved' | 'timeout' | 'skipped'

/** 需要人工接手（如人机验证）的请求卡片 */
export interface TakeoverPart {
  type: 'takeover'
  part_id: string
  task_id: string
  browser_session_id: string
  reason: string
  state: 'requested' | 'active' | 'resolved' | 'timeout' | 'skipped'
  deadline_time: string | null
}

export interface ErrorPart {
  type: 'error'
  part_id: string
  code: string
  message: string
  task_id?: string
}

export interface UnknownPart {
  type: string
  part_id: string
  [k: string]: unknown
}

export type MessagePart =
  | TextPart
  | ClarificationPart
  | PlanSummaryPart
  | ProgressPart
  | SourcePart
  | ArtifactPart
  | ErrorPart
  | TakeoverPart
  | HighlightsPart
  | SuggestionsPart

export interface MessageOut {
  message_id: string
  conversation_id: string
  turn_id: string
  role: 'user' | 'assistant'
  parts: MessagePart[]
  message_status: string
  mode_selection: string | null
  task_ids: string[]
  created_time: string
  updated_time: string
}

export interface MessageList {
  items: MessageOut[]
  last_event_seq_no: number
}

export interface MessageIn {
  client_message_id: string
  text: string
  mode_selection: ModeSelection
}

export interface SendMessageOut {
  user_message: MessageOut
  assistant_message: MessageOut
  deduplicated: boolean
}

// ---------------------------------------------------------------- 任务
export interface TaskOut {
  task_id: string
  conversation_id: string | null
  parent_task_id: string | null
  mode: string
  title: string
  task_status: TaskStatus
  status_reason: string | null
  current_stage: string | null
  cancel_generation: number
  plan_hash: string | null
  task_spec: Record<string, unknown>
  result_summary: Record<string, unknown> | null
  error_code: string | null
  error_desc: string | null
  llm_request_qty: number
  spent_minor_amt: number
  cost_unknown_qty: number
  created_time: string
  updated_time: string
}

export interface TaskControlResult {
  task_id: string
  outcome: 'accepted' | 'not_needed' | 'conflict' | 'forbidden'
  task_status: string | null
}

export interface StopTurnOut {
  turn_id: string | null
  results: TaskControlResult[]
}

export interface EvidenceOut {
  evidence_id: string
  quote_text: string
  claim_text: string | null
  verification_status: string
}

export interface SourceOut {
  n: number
  source_revision_id: string
  title: string | null
  request_url: string
  final_url: string | null
  site_name: string | null
  author: string | null
  publish_time_text: string | null
  retrieved_time: string
  access_method: string
  revision_status: string
  failure_reason: string | null
  evidence: EvidenceOut[]
}

export interface CandidateOut {
  candidate_id: string
  query_text: string
  engine_name: string
  rank_no: number
  url: string
  title: string | null
  snippet: string | null
  candidate_status: string
}

export interface TaskSourcesOut {
  sources: SourceOut[]
  candidates: CandidateOut[]
}

// ---------------------------------------------------------------- 浏览器阅览
export interface BrowserSessionOut {
  browser_session_id: string
  task_id: string
  session_label: string
  session_status: string
  current_url: string | null
  current_title: string | null
  current_activity: string | null
  frame_seq_no: number
  frame_time: string | null
  /** 是否支持实时画面（WebSocket） */
  live_available?: boolean
  handoff_state?: HandoffState
  handoff_reason?: string | null
  handoff_deadline?: string | null
}

export interface ViewerMetaOut extends BrowserSessionOut {
  preview_mode: 'snapshot' | 'live'
  connected: boolean
  stale: boolean
  masked: boolean
  task_status: string | null
}

// ---------------------------------------------------------------- 产物
export interface ArtifactOut {
  artifact_id: string
  task_id: string | null
  conversation_id: string | null
  artifact_kind: string
  display_name: string
  mime_name: string
  byte_qty: number
  record_qty: number | null
  content_hash: string
  quality_status: string
  artifact_status: string
  created_time: string
}

export interface LiveTicketOut {
  ticket: string
  expires_in: number
  interactive: boolean
}

/** 实时画面 WebSocket：服务端 → 客户端 */
export type LiveServerMsg =
  | { type: 'frame'; data: string; width: number; height: number; seq: number; url: string; title: string }
  | {
      type: 'status'
      session_status: string
      handoff_state: HandoffState
      handoff_reason: string | null
      handoff_deadline: string | null
      interactive: boolean
    }
  | { type: 'error'; message: string }

/** 实时画面 WebSocket：客户端 → 服务端（仅人工接手期间发送） */
export type LiveClientMsg =
  | {
      type: 'mouse'
      action: 'move' | 'down' | 'up' | 'wheel'
      x: number
      y: number
      button: 'left' | 'right' | 'middle'
      clickCount: number
      deltaX: number
      deltaY: number
    }
  | { type: 'key'; action: 'down' | 'up'; key: string; code: string; text: string | null }
  | { type: 'text'; text: string }

export interface ArtifactPreviewOut {
  kind: 'table' | 'markdown' | 'text' | 'html'
  content: string | null
  columns: string[] | null
  rows: unknown[][] | null
  total_rows: number | null
  shown_rows: number | null
}

// ---------------------------------------------------------------- 大模型管理
export interface ProviderPreset {
  provider_type: string
  provider_name: string
  base_url: string
  example_models: string[]
  note: string | null
}

export interface ProviderIn {
  provider_name: string
  provider_type: string
  base_url: string
  api_key?: string | null
  enabled: boolean
}

export interface ProviderPatch {
  provider_name?: string
  base_url?: string
  api_key?: string
  enabled?: boolean
}

export interface ProviderOut {
  provider_id: string
  provider_name: string
  provider_type: string
  base_url: string
  has_api_key: boolean
  api_key_mask: string | null
  enabled: boolean
}

export interface ModelIn {
  provider_id: string
  model_name: string
  display_name: string | null
  supports_tools: boolean
  /** 是否接受强制工具调用（tool_choice=required）；思考模式模型通常为 false，运行中会自动探测 */
  supports_forced_tool_choice: boolean
  supports_json_schema: boolean
  supports_json_object: boolean
  supports_vision: boolean
  context_window_qty: number | null
  max_output_qty: number | null
  input_price_minor_amt: number | null
  output_price_minor_amt: number | null
  currency_code: string
  enabled: boolean
}

export type ModelPatch = Partial<Omit<ModelIn, 'provider_id' | 'model_name'>>

export interface ModelOut extends ModelIn {
  model_profile_id: string
  provider_name: string | null
}

export interface ModelTestOut {
  ok: boolean
  latency_ms: number | null
  reply: string | null
  error: string | null
  /** 结构化输出（智能体实际使用方式）是否可用 */
  structured_ok?: boolean | null
  /** 测试中自动调整的能力配置说明 */
  adaptations?: string[]
}

export interface AgentBindingIn {
  model_profile_id: string
  fallback_profile_ids: string[]
  temperature: number | null
  max_tokens: number | null
}

export interface AgentBindingOut {
  agent_role: string
  role_label: string
  description: string
  model_profile_id: string | null
  fallback_profile_ids: string[]
  temperature: number | null
  max_tokens: number | null
}
