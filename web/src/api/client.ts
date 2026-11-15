// 轻量 fetch 封装：统一 Bearer、错误解析与 401 处理。
import type {
  AdminDebugStatus,
  AdminAgentRun,
  AdminOverview,
  AdminSettings,
  AdminTask,
  AdminTaskDetail,
  AdminUser,
  AdminUserDetail,
  DiagnoseOut,
  FileContentOut,
  FileOut,
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

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

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

  // 上传文件
  listFiles: (cid: string) => get<FileOut[]>(`/conversations/${enc(cid)}/files`),
  getFile: (id: string) => get<FileOut>(`/files/${enc(id)}`),
  fileContent: (id: string) => get<FileContentOut>(`/files/${enc(id)}/content`),
  reparseFile: (id: string) => post<FileOut>(`/files/${enc(id)}/reparse`),
  deleteFile: (id: string) => del<void>(`/files/${enc(id)}`),
  downloadFile: async (id: string, filename: string) => {
    const res = await rawFetch(`/files/${enc(id)}/download`)
    saveBlob(await res.blob(), filename)
  },
  /** 上传单个文件（XHR，便于显示上传进度） */
  uploadFile: (cid: string, file: File, onProgress?: (pct: number) => void, signal?: AbortSignal) =>
    new Promise<FileOut>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API_BASE}/conversations/${enc(cid)}/files`)
      const t = getToken()
      if (t) xhr.setRequestHeader('Authorization', `Bearer ${t}`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      }
      xhr.onload = () => {
        let body: unknown = null
        try {
          body = JSON.parse(xhr.responseText)
        } catch {
          /* ignore */
        }
        if (xhr.status === 401) unauthorizedHandler?.()
        if (xhr.status >= 200 && xhr.status < 300 && Array.isArray(body) && body.length) resolve(body[0] as FileOut)
        else reject(new ApiError(xhr.status, errorMessage(xhr.status, body), body))
      }
      xhr.onerror = () => reject(new ApiError(0, '网络连接失败，请检查网络后重试'))
      xhr.onabort = () => reject(new ApiError(0, '已取消上传'))
      signal?.addEventListener('abort', () => xhr.abort())
      const fd = new FormData()
      fd.append('files', file, file.name)
      xhr.send(fd)
    }),

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
  /** 下载任务执行日志（排查问题时发给开发者） */
  downloadTaskTrace: async (taskId: string) => {
    const res = await rawFetch(`/tasks/${enc(taskId)}/trace`)
    const cd = res.headers.get('content-disposition') || ''
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd)
    saveBlob(await res.blob(), m ? decodeURIComponent(m[1]) : `执行日志_${taskId}.log`)
  },
  /** 管理员：下载调试日志包（ZIP）。传 taskId 只导出该任务；否则导出最近 hours 小时的整个系统 */
  downloadDebugBundle: async (o: { taskId?: string; hours?: number; includeText?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (o.taskId) q.set('task_id', o.taskId)
    if (o.hours) q.set('hours', String(o.hours))
    q.set('include_text', o.includeText === false ? 'false' : 'true')
    const res = await rawFetch(`/admin/debug/bundle?${q}`)
    const cd = res.headers.get('content-disposition') || ''
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd)
    saveBlob(await res.blob(), m ? decodeURIComponent(m[1]) : '调试日志.zip')
  },
  adminDebugStatus: () => get<AdminDebugStatus>('/admin/debug/status'),
  downloadArtifact: async (id: string, filename: string) => {
    const res = await rawFetch(`/artifacts/${enc(id)}/download`)
    saveBlob(await res.blob(), filename)
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
  /** 取消单独绑定，改用默认模型 */
  deleteAgentBinding: (role: string) => del<void>(`/admin/llm/agent-bindings/${enc(role)}`),

  // 管理后台：概览、记录、用户、运行参数
  adminOverview: (days = 14) => get<AdminOverview>(`/admin/overview?days=${days}`),
  adminRuns: (q: PageQuery & { role?: string; status?: string }) => get<Paged<AdminAgentRun>>(`/admin/agent-runs${qs(q)}`),
  adminTasks: (q: PageQuery & { status?: string; mode?: string }) => get<Paged<AdminTask>>(`/admin/tasks${qs(q)}`),
  adminTask: (id: string) => get<AdminTaskDetail>(`/admin/tasks/${enc(id)}`),
  adminUsers: (q: PageQuery) => get<Paged<AdminUser>>(`/admin/users${qs(q)}`),
  adminUser: (id: string) => get<AdminUserDetail>(`/admin/users/${enc(id)}`),
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
