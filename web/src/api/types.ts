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

export type Credibility = 'user_file' | 'official' | 'academic' | 'media' | 'reference' | 'community' | 'aggregate' | 'unknown'

export interface Citation {
  n: number
  source_revision_id: string
  url: string
  title: string | null
  site_name?: string | null
  publish_time_text?: string | null
  credibility?: Credibility
  credibility_label?: string
  file_id?: string | null
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
  stages: { key: string; label: string; status: StageStatus; elapsed_ms?: number | null }[]
  /** 耗时与消耗：开始/结束时间（毫秒时间戳）、总耗时、模型调用次数、费用（分） */
  metrics?: {
    started_ms: number | null
    finished_ms: number | null
    elapsed_ms: number | null
    llm_requests: number
    spent_minor_amt: number
    cost_unknown_qty: number
  }
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
  access_method?: string
  file_id?: string | null
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

/** 撰写中的实时草稿（流式显示，完成后由最终成果替代） */
export interface DraftPart {
  type: 'draft'
  part_id: string
  task_id: string
  kind: 'answer' | 'report'
  title: string
  text: string
  chars: number
  status: 'writing'
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
  | DraftPart
  | FilePart

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
  /** 随消息发送的已上传文件 */
  file_ids?: string[]
}

// ---------------------------------------------------------------- 上传文件
export type FileParseStatus = 'queued' | 'parsing' | 'parsed' | 'failed'

export interface FileOut {
  file_id: string
  conversation_id: string | null
  message_id: string | null
  name: string
  mime: string
  ext: string
  byte_qty: number
  parse_status: FileParseStatus
  parse_status_label: string
  parser: string | null
  parse_detail: string | null
  parse_error: string | null
  page_qty: number | null
  char_qty: number | null
  table_qty: number | null
  image_qty: number | null
  outline: string[]
  created_time: string | null
}

export interface FileContentOut {
  file: FileOut
  markdown: string
  truncated: boolean
}

/** 用户消息里的附件（随解析状态实时更新） */
export interface FilePart {
  type: 'file'
  part_id: string
  file_id: string
  name: string
  ext: string
  byte_qty: number
  parse_status: FileParseStatus
  parse_detail: string | null
  parse_error: string | null
  page_qty: number | null
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
  | { type: 'reload' }
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

// ---------------------------------------------------------------- 管理后台：概览、记录、设置
export interface Paged<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface AdminOverview {
  totals: {
    users: number
    conversations: number
    tasks: number
    tasks_active: number
    artifacts: number
    sources_read: number
  }
  task_status: Record<string, number>
  tasks_by_day: { date: string; total: number; completed: number; failed: number }[]
  llm: {
    requests: number
    input_tokens: number
    output_tokens: number
    failed_runs: number
    unknown_cost_runs: number
    cost: { currency_code: string; minor_amt: number }[]
  }
  llm_by_role: {
    role: string
    label: string
    requests: number
    input_tokens: number
    output_tokens: number
    failed: number
    avg_ms: number | null
  }[]
  llm_by_model: { provider_name: string | null; model_name: string | null; requests: number; input_tokens: number; output_tokens: number }[]
  recent_failures: {
    kind: 'task' | 'agent_run'
    id: string
    title: string
    detail: string | null
    time: string
    conversation_id: string | null
  }[]
  engines: { name: string; label: string; kind: 'general' | 'vertical'; enabled: boolean; cooldown_until: string | null }[]
}

export interface AdminAgentRun {
  agent_run_id: string
  task_id: string | null
  conversation_id: string | null
  agent_role: string
  role_label: string
  provider_name: string | null
  model_name: string | null
  request_qty: number
  input_token_qty: number
  output_token_qty: number
  cost_minor_amt: number | null
  currency_code: string | null
  cost_status: string
  run_status: string
  error_desc: string | null
  started_time: string
  finished_time: string | null
  duration_ms: number | null
}

export interface AdminTask {
  task_id: string
  title: string
  mode: string
  task_status: string
  status_reason: string | null
  current_stage: string | null
  username: string | null
  display_name: string | null
  conversation_id: string | null
  llm_request_qty: number
  spent_minor_amt: number
  cost_unknown_qty: number
  created_time: string
  updated_time: string
  /** 总耗时（毫秒，进行中的任务为至今） */
  elapsed_ms?: number | null
  /** 各阶段累计耗时（毫秒） */
  stage_ms?: Record<string, number>
}

export interface AdminUser {
  user_id: string
  username: string
  display_name: string | null
  is_admin: boolean
  user_status: 'active' | 'disabled'
  created_time: string
  conversation_qty: number
  task_qty: number
}

export type SettingType = 'engine_order' | 'select' | 'multi' | 'int' | 'bool'
/** 任务详情（后台抽屉） */
export interface AdminTaskDetail {
  task: AdminTask
  spec: { requirement_text: string | null; questions: string[]; limits: Record<string, number>; output_formats: string[] }
  error_desc: string | null
  runs: {
    run_id: string
    run_seq_no: number
    run_status: string
    worker_id: string | null
    started_time: string | null
    finished_time: string | null
    duration_ms: number | null
  }[]
  steps: {
    step_id: string
    node_id: string
    node_kind: string
    agent_role: string | null
    role_label: string | null
    step_status: string
    attempt_no: number
    error_desc: string | null
    started_time: string | null
    duration_ms: number | null
  }[]
  sources: {
    by_status: Record<string, number>
    items: {
      source_no: number | null
      title: string | null
      url: string
      site_name: string | null
      revision_status: string
      failure_reason: string | null
      credibility_label: string
    }[]
  }
  llm: { requests: number; input_tokens: number; output_tokens: number; calls: number; failed: number }
  artifacts: {
    artifact_id: string
    display_name: string
    artifact_kind: string
    byte_qty: number
    record_qty: number | null
    created_time: string
  }[]
}

export interface AdminUserDetail {
  user: AdminUser
  llm_requests: number
  tokens: number
  recent_tasks: AdminTask[]
}

export type SettingValue = string | number | boolean | string[] | null

export interface SettingField {
  key: string
  label: string
  group: 'search' | 'task' | 'browser'
  type: SettingType
  value: SettingValue
  default: SettingValue
  options: { value: string; label: string }[] | null
  min: number | null
  max: number | null
  help: string
  overridden: boolean
}

export interface AdminSettings {
  fields: SettingField[]
  static: { group: string; items: { label: string; value: string }[] }[]
  config_path: string
}

export type DiagnoseStatus = 'ok' | 'empty' | 'irrelevant' | 'blocked' | 'unreachable' | 'error'

export interface DiagnoseResult {
  name: string
  label: string
  status: DiagnoseStatus
  count: number
  seconds: number
  sample: string | null
  detail: string | null
}

export interface DiagnoseOut {
  browser: string
  proxy: string | null
  results: DiagnoseResult[]
}
