// 首页快捷入口与应用启动器共用的动作列表。模式类动作只切换模式并预填示例文字，从不自动发送。
import type { Component } from 'vue'
import type { Router } from 'vue-router'
import { BookOpen, Bot, Database, FileBarChart, FileText, MessageSquare, Search, Settings } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'

export interface HomeAction {
  key: string
  label: string
  icon: Component
  /** 图标颜色（Tailwind 文本色）与浅色圆底 */
  color: string
  tint: string
  mode?: ModeSelection
  example?: string
  adminOnly?: boolean
  launcherOnly?: boolean
}

export const HOME_ACTIONS: HomeAction[] = [
  { key: 'quick_search', label: '搜索问题', icon: Search, color: 'text-sky-500', tint: 'bg-sky-500/12', mode: 'quick_search', example: '帮我查一下：' },
  { key: 'research', label: '深入研究', icon: BookOpen, color: 'text-violet-500', tint: 'bg-violet-500/12', mode: 'research', example: '帮我研究一下这个主题，并生成带引用的报告：' },
  { key: 'dataset', label: '采集数据', icon: Database, color: 'text-emerald-500', tint: 'bg-emerald-500/12', mode: 'dataset', example: '帮我采集以下数据并整理成表格：' },
  { key: 'hybrid', label: '数据+报告', icon: FileBarChart, color: 'text-amber-500', tint: 'bg-amber-500/12', mode: 'hybrid', example: '帮我采集相关数据并生成分析报告：' },
  { key: 'history', label: '最近对话', icon: MessageSquare, color: 'text-indigo-500', tint: 'bg-indigo-500/12' },
  { key: 'artifacts', label: '我的成果', icon: FileText, color: 'text-rose-500', tint: 'bg-rose-500/12' },
  { key: 'settings', label: '设置', icon: Settings, color: 'text-slate-500', tint: 'bg-slate-500/12', launcherOnly: true },
  { key: 'admin', label: '管理后台', icon: Bot, color: 'text-fuchsia-500', tint: 'bg-fuchsia-500/12', adminOnly: true },
]

export function visibleActions(isAdmin: boolean, where: 'home' | 'launcher'): HomeAction[] {
  return HOME_ACTIONS.filter((a) => (!a.adminOnly || isAdmin) && (where === 'launcher' || !a.launcherOnly))
}

/** 执行动作。模式类动作：跳转到首页并带上 mode/prefill 参数，由首页预填输入框（不发送）。 */
export function runHomeAction(a: HomeAction, router: Router, openHistory: () => void) {
  if (a.mode) {
    void router.push({ name: 'home', query: { mode: a.mode, prefill: '1' } })
    return
  }
  if (a.key === 'history') openHistory()
  else if (a.key === 'artifacts') void router.push({ name: 'artifacts' })
  else if (a.key === 'settings') void router.push({ name: 'settings' })
  else if (a.key === 'admin') void router.push({ name: 'admin-llm' })
}
