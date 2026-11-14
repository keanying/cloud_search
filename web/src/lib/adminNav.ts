import type { Component } from 'vue'
import { Activity, Boxes, Cpu, Gauge, LayoutDashboard, ListChecks, Network, Plug, Search, Users } from 'lucide-vue-next'

export interface AdminNavItem {
  name: string
  label: string
  icon: Component
  desc: string
}

/** 管理后台导航（分组）；name 即路由名 */
export const ADMIN_NAV: { group: string | null; items: AdminNavItem[] }[] = [
  {
    group: null,
    items: [{ name: 'admin-overview', label: '概览', icon: LayoutDashboard, desc: '任务、模型调用与搜索引擎的整体情况' }],
  },
  {
    group: '模型',
    items: [
      { name: 'admin-providers', label: '供应方', icon: Plug, desc: '接入 OpenAI、DeepSeek、Kimi、火山方舟、通义千问、智谱等 OpenAI 兼容接口' },
      { name: 'admin-models', label: '模型', icon: Cpu, desc: '登记可用模型、能力矩阵与单价，并测试连通与结构化输出' },
      { name: 'admin-agents', label: '智能体分工', icon: Network, desc: '为八个智能体分别指定主模型、备用模型与生成参数' },
    ],
  },
  {
    group: '运行',
    items: [
      { name: 'admin-search', label: '搜索与浏览器', icon: Search, desc: '搜索引擎顺序、垂直来源、冷却策略与人工接手；检测本机网络下的引擎可用性' },
      { name: 'admin-limits', label: '任务限额', icon: Gauge, desc: '每个任务的搜索、阅读、并发与模型调用上限' },
    ],
  },
  {
    group: '数据',
    items: [
      { name: 'admin-tasks', label: '任务', icon: ListChecks, desc: '所有用户发起的任务及其状态与消耗' },
      { name: 'admin-runs', label: '调用记录', icon: Activity, desc: '每一次智能体模型调用：耗时、token 与费用' },
      { name: 'admin-users', label: '用户', icon: Users, desc: '账号、管理员权限与停用' },
    ],
  },
]

export const ADMIN_ITEMS = ADMIN_NAV.flatMap((g) => g.items)
export const ADMIN_ICON_FALLBACK = Boxes
