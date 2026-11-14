// 轻量 fetch 封装：统一 Bearer、错误解析与 401 处理。
import type {
  AdminAgentRun,
  AdminOverview,
  AdminSettings,
  AdminTask,
  AdminUser,
  DiagnoseOut,
  Paged,
  SettingValue,
  AgentBindingIn,
  AgentBindingOut,
  ArtifactOut,
  ArtifactPreviewOut,
  BrowserSessionOut,
  ConversationList,
  ConversationOut,
  MessageIn,
  MessageList,
  ModelIn,
  ModelOut,
  ModelPatch,
  ModelTestOut,
  ProviderIn,
  ProviderOut,
  ProviderPatch,
  ProviderPreset,
  SendMessageOut,
  StopTurnOut,
  TaskOut,
  TaskSourcesOut,
  TokenOut,
  UserOut,
  ViewerMetaOut,
  LiveTicketOut,
} from './types'

export const API_BASE = '/api/v1'
const TOKEN_KEY = 'cs_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

let unauthorizedHandler: (() => void) | null = null
export function onUnauthorized(fn: () => void) {
  unauthorizedHandler = fn
}

export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) }
  const t = getToken()
  if (t) h.Authorization = `Bearer ${t}`
  return h
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d
        .map((x) => (x && typeof x === 'object' && 'msg' in x ? String((x as { msg: unknown }).msg) : String(x)))
        .join('；')
    }
    if (d && typeof d === 'object' && 'message' in d) return String((d as { message: unknown }).message)
  }
  if (status === 0) return '网络连接失败'
  if (status >= 500) return `服务暂不可用（${status}）`
  return `请求失败（${status}）`
}

export async function rawFetch(path: string, init: RequestInit = {}): Promise<Response> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers: authHeaders(init.headers as Record<string, string> | undefined),
    })
  } catch (e) {
    if (e instanceof DOMException && (e.name === 'TimeoutError' || e.name === 'AbortError'))
      throw new ApiError(0, '请求超时，请稍后重试')
    throw new ApiError(0, '网络连接失败，请检查网络后重试')
  }
  if (res.status === 401) {
    unauthorizedHandler?.()
  }
  if (!res.ok) {
    let body: unknown = null
    try {
      body = await res.json()
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, errorMessage(res.status, body), body)
  }
  return res
}

async function request<T>(method: string, path: string, body?: unknown, timeoutMs?: number): Promise<T> {
  const init: RequestInit = { method }
  if (timeoutMs) init.signal = AbortSignal.timeout(timeoutMs)
  if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  const res = await rawFetch(path, init)
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

const get = <T>(p: string) => request<T>('GET', p)
const post = <T>(p: string, b?: unknown) => request<T>('POST', p, b ?? {})
const patch = <T>(p: string, b: unknown) => request<T>('PATCH', p, b)
const put = <T>(p: string, b: unknown) => request<T>('PUT', p, b)
const del = <T>(p: string) => request<T>('DELETE', p)

const enc = encodeURIComponent

export const api = {
  // 认证
  register: (b: { username: string; password: string; display_name?: string | null }) =>
    post<TokenOut>('/auth/register', b),
  login: (b: { username: string; password: string }) => post<TokenOut>('/auth/login', b),
  me: () => get<UserOut>('/auth/me'),

  // 会话
  listConversations: (limit = 30, cursor?: string | null) =>
    get<ConversationList>(`/conversations?limit=${limit}${cursor ? `&cursor=${enc(cursor)}` : ''}`),
  createConversation: (title?: string) => post<ConversationOut>('/conversations', title ? { title } : {}),
  getConversation: (id: string) => get<ConversationOut>(`/conversations/${enc(id)}`),
  patchConversation: (id: string, b: { title?: string; conversation_status?: 'active' | 'archived' }) =>
    patch<ConversationOut>(`/conversations/${enc(id)}`, b),
  deleteConversation: (id: string) => del<void>(`/conversations/${enc(id)}`),
  listMessages: (id: string) => get<MessageList>(`/conversations/${enc(id)}/messages`),
  sendMessage: (id: string, b: MessageIn) => post<SendMessageOut>(`/conversations/${enc(id)}/messages`, b),
  conversationTasks: (id: string) => get<TaskOut[]>(`/conversations/${enc(id)}/tasks`),
  stopTurn: (id: string, turnId?: string | null) =>
    post<StopTurnOut>(`/conversations/${enc(id)}/stop-turn`, turnId ? { turn_id: turnId } : {}),

  // 任务
  getTask: (id: string) => get<TaskOut>(`/tasks/${enc(id)}`),
  confirmTask: (id: string, planHash: string) => post<TaskOut>(`/tasks/${enc(id)}/confirm`, { plan_hash: planHash }),
  stopTask: (id: string) => post<TaskOut>(`/tasks/${enc(id)}/stop`),
  pauseTask: (id: string) => post<TaskOut>(`/tasks/${enc(id)}/pause`),
  resumeTask: (id: string) => post<TaskOut>(`/tasks/${enc(id)}/resume`),
  continueTask: (id: string) => post<TaskOut>(`/tasks/${enc(id)}/continue`),
  taskSources: (id: string) => get<TaskSourcesOut>(`/tasks/${enc(id)}/sources`),
  taskBrowserSessions: (id: string) => get<BrowserSessionOut[]>(`/tasks/${enc(id)}/browser-sessions`),

  // 阅览（只读）
  viewerMeta: (id: string) => get<ViewerMetaOut>(`/browser-sessions/${enc(id)}/viewer-meta`),
  viewerSnapshot: async (id: string): Promise<Blob | null> => {
    try {
      const res = await rawFetch(`/browser-sessions/${enc(id)}/viewer-snapshot`)
      return await res.blob()
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null
      throw e
    }
  },

  // 实时画面与人工接手
  liveTicket: (id: string) => post<LiveTicketOut>(`/browser-sessions/${enc(id)}/live-ticket`),
  liveUrl: (id: string, ticket: string) => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}${API_BASE}/browser-sessions/${enc(id)}/live?ticket=${enc(ticket)}`
  },
  takeover: (id: string) => post<ViewerMetaOut>(`/browser-sessions/${enc(id)}/takeover`),
  takeoverReturn: (id: string, resolved: boolean) =>
    post<ViewerMetaOut>(`/browser-sessions/${enc(id)}/takeover/return`, { resolved }),

  // 产物
  listArtifacts: () => get<ArtifactOut[]>('/artifacts'),
  getArtifact: (id: string) => get<ArtifactOut>(`/artifacts/${enc(id)}`),
  artifactPreview: (id: string) => get<ArtifactPreviewOut>(`/artifacts/${enc(id)}/preview`),
  downloadArtifact: async (id: string, filename: string) => {
    const res = await rawFetch(`/artifacts/${enc(id)}/download`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
  },

  // 大模型管理
  providerPresets: () => get<ProviderPreset[]>('/admin/llm/provider-presets'),
  listProviders: () => get<ProviderOut[]>('/admin/llm/providers'),
  createProvider: (b: ProviderIn) => post<ProviderOut>('/admin/llm/providers', b),
  patchProvider: (id: string, b: ProviderPatch) => patch<ProviderOut>(`/admin/llm/providers/${enc(id)}`, b),
  deleteProvider: (id: string) => del<void>(`/admin/llm/providers/${enc(id)}`),
  listModels: () => get<ModelOut[]>('/admin/llm/models'),
  createModel: (b: ModelIn) => post<ModelOut>('/admin/llm/models', b),
  patchModel: (id: string, b: ModelPatch) => patch<ModelOut>(`/admin/llm/models/${enc(id)}`, b),
  deleteModel: (id: string) => del<void>(`/admin/llm/models/${enc(id)}`),
  testModel: (id: string) => post<ModelTestOut>(`/admin/llm/models/${enc(id)}/test`),
  agentBindings: () => get<AgentBindingOut[]>('/admin/llm/agent-bindings'),
  putAgentBinding: (role: string, b: AgentBindingIn) =>
    put<AgentBindingOut>(`/admin/llm/agent-bindings/${enc(role)}`, b),

  // 管理后台：概览、记录、用户、运行参数
  adminOverview: (days = 14) => get<AdminOverview>(`/admin/overview?days=${days}`),
  adminRuns: (q: PageQuery & { role?: string; status?: string }) => get<Paged<AdminAgentRun>>(`/admin/agent-runs${qs(q)}`),
  adminTasks: (q: PageQuery & { status?: string; mode?: string }) => get<Paged<AdminTask>>(`/admin/tasks${qs(q)}`),
  adminUsers: (q: PageQuery) => get<Paged<AdminUser>>(`/admin/users${qs(q)}`),
  patchAdminUser: (id: string, b: { is_admin?: boolean; user_status?: 'active' | 'disabled' }) =>
    patch<AdminUser>(`/admin/users/${enc(id)}`, b),
  adminSettings: () => get<AdminSettings>('/admin/settings'),
  putAdminSettings: (values: Record<string, SettingValue>) => put<AdminSettings>('/admin/settings', { values }),
  resetAdminSetting: (key: string) => del<AdminSettings>(`/admin/settings/${enc(key)}`),
  /** 引擎检测较慢（真实打开浏览器访问），单个引擎最长约 1 分钟 */
  diagnoseSearch: (query: string, engines: string[] | null) =>
    request<DiagnoseOut>('POST', '/admin/search/diagnose', { query, engines }, 120_000),
}

export interface PageQuery {
  page?: number
  size?: number
  q?: string
}

/** 查询串：忽略空值 */
function qs(o: object): string {
  const parts = Object.entries(o as Record<string, unknown>)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${enc(k)}=${enc(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}
