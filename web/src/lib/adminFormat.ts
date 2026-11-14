// 管理后台通用格式化：数量、费用、耗时、状态色调
import { taskStatusTone, type Tone } from './format'

export type Pastel = 'mint' | 'sky' | 'lilac' | 'butter' | 'peach' | 'gray'

export function pastelOf(t: Tone): Pastel {
  return ({ success: 'mint', info: 'sky', warning: 'butter', danger: 'peach', neutral: 'gray' } as const)[t]
}
export const taskPastel = (s: string | null | undefined): Pastel => pastelOf(taskStatusTone(s))

/** 1234 → 1,234；12345 → 1.2万；1.2亿 */
export function compact(n: number | null | undefined): string {
  if (n == null) return '—'
  const a = Math.abs(n)
  if (a >= 1e8) return `${(n / 1e8).toFixed(a >= 1e9 ? 0 : 1)}亿`
  if (a >= 1e4) return `${(n / 1e4).toFixed(a >= 1e5 ? 0 : 1)}万`
  return n.toLocaleString('zh-CN')
}

/** 金额（分 → 元，带币种） */
export function money(minor: number | null | undefined, currency: string | null | undefined): string {
  if (minor == null) return '—'
  const v = (minor / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (!currency || currency === 'CNY') return `¥${v}`
  if (currency === 'USD') return `$${v}`
  return `${v} ${currency}`
}

export function duration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`
  const m = Math.floor(ms / 60_000)
  return `${m} 分 ${Math.round((ms % 60_000) / 1000)} 秒`
}

export const RUN_STATUS: Record<string, { label: string; tone: Pastel }> = {
  succeeded: { label: '成功', tone: 'mint' },
  failed: { label: '失败', tone: 'peach' },
  rejected: { label: '被拒', tone: 'butter' },
  cancelled: { label: '已取消', tone: 'gray' },
  running: { label: '进行中', tone: 'sky' },
}
export const runStatus = (s: string) => RUN_STATUS[s] ?? { label: s, tone: 'gray' as Pastel }

export const TASK_STATUS_FILTER = [
  { value: 'running', label: '执行中', dot: 'var(--pastel-sky-dot)' },
  { value: 'queued', label: '排队中', dot: 'var(--pastel-sky-dot)' },
  { value: 'completed', label: '执行结束', dot: 'var(--pastel-mint-dot)' },
  { value: 'partial_failed', label: '部分失败', dot: 'var(--pastel-butter-dot)' },
  { value: 'failed', label: '失败', dot: 'var(--pastel-peach-dot)' },
  { value: 'stopped', label: '已停止', dot: 'var(--pastel-butter-dot)' },
  { value: 'draft', label: '草稿', dot: 'var(--color-slate-500)' },
]
export const TASK_MODE_FILTER = [
  { value: 'quick_search', label: '搜索问题' },
  { value: 'research', label: '深入研究' },
  { value: 'dataset', label: '采集数据' },
  { value: 'hybrid', label: '数据+报告' },
]

/** 稳定的头像底色（按字符串散列） */
export function hueTone(s: string): Exclude<Pastel, 'gray'> {
  const tones = ['mint', 'sky', 'lilac', 'butter', 'peach'] as const
  let h = 0
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) % 1000003
  return tones[h % tones.length]
}

/** 执行轮次 / 步骤状态 */
export const STEP_STATUS: Record<string, { label: string; tone: Pastel }> = {
  succeeded: { label: '完成', tone: 'mint' },
  completed: { label: '完成', tone: 'mint' },
  running: { label: '进行中', tone: 'sky' },
  queued: { label: '排队', tone: 'gray' },
  failed: { label: '失败', tone: 'peach' },
  partial_failed: { label: '部分失败', tone: 'butter' },
  cancelled: { label: '已取消', tone: 'gray' },
  stopped: { label: '已停止', tone: 'gray' },
  paused: { label: '已暂停', tone: 'butter' },
  skipped: { label: '跳过', tone: 'gray' },
}
export const stepStatus = (s: string) => STEP_STATUS[s] ?? { label: s, tone: 'gray' as Pastel }

const NODE_LABEL: Record<string, string> = {
  plan: '规划搜索',
  search: '搜索',
  select: '挑选候选',
  read: '读取网页',
  extract: '抽取证据',
  coverage: '覆盖评估',
  verify: '核验',
  build: '整理数据',
  analyze: '计算分析',
  write: '撰写',
}
/** 步骤节点 ID（如 extract:sr_x、coverage:w1）→ 中文名 */
export function nodeLabel(nodeId: string): string {
  const head = nodeId.split(':')[0]
  return NODE_LABEL[head] ?? head
}

export const REVISION_STATUS: Record<string, { label: string; tone: Pastel }> = {
  captured: { label: '已读取', tone: 'mint' },
  blocked: { label: '访问受限', tone: 'butter' },
  failed: { label: '读取失败', tone: 'peach' },
  no_content: { label: '无正文', tone: 'gray' },
}
export const revisionStatus = (s: string) => REVISION_STATUS[s] ?? { label: s, tone: 'gray' as Pastel }
