import type { ModeSelection, TaskStatus } from '@/api/types'

/** PRD 第四章：任务内部状态 → 前台文案 */
export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  draft: '草稿',
  ready: '已就绪',
  queued: '排队中',
  running: '执行中',
  pausing: '暂停中',
  paused: '已暂停',
  stopping: '停止中',
  stopped: '已停止',
  completed: '执行结束',
  partial_failed: '部分失败',
  failed: '失败',
  cancelled: '已取消',
}

export function taskStatusLabel(status: string | null | undefined, reason?: string | null): string {
  if (!status) return '未知'
  if (status === 'draft' && (reason === 'approval' || reason === 'awaiting_confirmation')) return '等待确认'
  if (status === 'draft' && reason === 'clarification') return '等待补充'
  return TASK_STATUS_LABEL[status as TaskStatus] ?? status
}

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export function taskStatusTone(status: string | null | undefined): Tone {
  switch (status) {
    case 'running':
    case 'queued':
    case 'ready':
      return 'info'
    case 'completed':
      return 'success'
    case 'pausing':
    case 'paused':
    case 'stopping':
    case 'stopped':
    case 'partial_failed':
    case 'draft':
      return 'warning'
    case 'failed':
    case 'cancelled':
      return 'danger'
    default:
      return 'neutral'
  }
}

/** 状态胶囊上的 emoji：执行中 ⏳、已完成 ✅、需要你 ✋、已停止 ⏹ */
export function taskStatusEmoji(status: string | null | undefined, reason?: string | null): string {
  if (status === 'draft' && reason && reason !== 'none') return '✋'
  switch (status) {
    case 'queued':
    case 'ready':
    case 'running':
    case 'pausing':
    case 'stopping':
      return '⏳'
    case 'completed':
      return '✅'
    case 'paused':
      return '⏸'
    case 'stopped':
    case 'cancelled':
      return '⏹'
    case 'partial_failed':
    case 'failed':
      return '⚠️'
    case 'draft':
      return '✋'
    default:
      return '•'
  }
}

/** 正在占用云端执行（可被“停止当前轮”控制）的状态 */
export const ACTIVE_STATUSES: ReadonlySet<string> = new Set(['queued', 'running', 'pausing', 'stopping'])
export const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  'stopped',
  'completed',
  'partial_failed',
  'failed',
  'cancelled',
])

export const MODE_OPTIONS: { value: ModeSelection; label: string; desc: string }[] = [
  { value: 'auto', label: '智能模式', desc: '根据需求建议执行路线，可修改' },
  { value: 'quick_search', label: '搜索问题', desc: '快速搜索并给出带来源的回答' },
  { value: 'research', label: '深入研究', desc: '多来源研究并生成引用报告' },
  { value: 'dataset', label: '采集数据', desc: '按字段采集并整理为数据文件' },
  { value: 'hybrid', label: '数据+报告', desc: '采集数据并生成分析报告' },
]

export function modeLabel(mode: string | null | undefined): string {
  return MODE_OPTIONS.find((m) => m.value === mode)?.label ?? mode ?? ''
}

export const ARTIFACT_KIND_LABEL: Record<string, string> = {
  answer: '回答',
  report: '报告',
  dataset: '数据',
  data_dictionary: '数据字典',
  sources: '来源清单',
}

export function artifactKindLabel(kind: string): string {
  return ARTIFACT_KIND_LABEL[kind] ?? kind
}

export const ACCESS_METHOD_LABEL: Record<string, string> = {
  browser: '云端浏览器读取',
  http: 'HTTP 读取',
  user_file: '用户文件',
  authorized_api: '授权接口',
}

export const QUALITY_LABEL: Record<string, string> = {
  unreviewed: '未审核',
  machine_checked: '机器检查',
  pending_review: '待人审',
  needs_revision: '需修订',
  approved: '已人审',
  rejected: '已驳回',
  candidate: '候选',
  conflicted: '存在冲突',
}

export function qualityLabel(s: string | null | undefined): string {
  if (!s) return ''
  return QUALITY_LABEL[s] ?? s
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

/** 后端返回 UTC（可能无 Z 后缀），统一按 UTC 解析 */
export function parseTime(s: string | null | undefined): Date | null {
  if (!s) return null
  const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatTime(s: string | null | undefined): string {
  const d = parseTime(s)
  if (!d) return '—'
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  if (sameDay) return `${hh}:${mm}:${ss}`
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hh}:${mm}`
}

export function relativeTime(s: string | null | undefined): string {
  const d = parseTime(s)
  if (!d) return '—'
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return ''
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

export function greeting(): string {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
}

/** 来源可信度 → 色调（与卡片 pastel 色一致） */
export function credibilityTone(c: string | null | undefined): 'mint' | 'sky' | 'lilac' | 'butter' | 'peach' | null {
  switch (c) {
    case 'user_file':
    case 'official':
      return 'mint'
    case 'academic':
      return 'lilac'
    case 'media':
      return 'sky'
    case 'reference':
      return 'butter'
    case 'aggregate':
      return 'peach'
    default:
      return null
  }
}
