import type { Component } from 'vue'
import { Activity, Boxes, Cpu, LayoutDashboard, ListChecks, Network, Radar, SlidersHorizontal, Users } from 'lucide-vue-next'

export interface AdminNavItem {
  name: string
  label: string
  icon: Component
  desc: string
  /** 命令面板里的额外搜索关键词 */
  keywords?: string
}

/** 管理后台导航（分组）；name 即路由名 */
export const ADMIN_NAV: { group: string | null; items: AdminNavItem[] }[] = [
  {
    group: null,
    items: [{ name: 'admin-overview', label: '概览', icon: LayoutDashboard, desc: '任务、模型调用与搜索引擎的整体情况' }],
  },
  {
    group: '模型服务',
    items: [
      {
        name: 'admin-models',
        label: '模型与供应方',
        icon: Cpu,
        desc: '接入 OpenAI 兼容接口的供应方，登记模型能力与单价，并测试连通与结构化输出',
        keywords: '供应方 provider openai deepseek kimi 火山 通义 智谱 api key 密钥 测试',
      },
      {
        name: 'admin-agents',
        label: '智能体分工',
        icon: Network,
        desc: '为八个智能体分别指定主模型、备用模型与生成参数；未指定的使用默认模型',
        keywords: '绑定 默认模型 备用 温度',
      },
    ],
  },
  {
    group: '运行配置',
    items: [
      {
        name: 'admin-settings',
        label: '运行参数',
        icon: SlidersHorizontal,
        desc: '搜索引擎、垂直来源、冷却策略、人工接手与任务限额；保存后对新任务立即生效',
        keywords: '搜索引擎 顺序 垂直来源 冷却 人工接手 验证码 任务限额 上限 config.yaml',
      },
      {
        name: 'admin-diagnose',
        label: '引擎检测',
        icon: Radar,
        desc: '用服务器上的浏览器真实打开每个搜索引擎，判断当前网络与代理下哪些可用',
        keywords: '检测 可用性 代理 proxy 人机验证',
      },
    ],
  },
  {
    group: '记录',
    items: [
      { name: 'admin-tasks', label: '任务', icon: ListChecks, desc: '所有用户发起的任务：状态、步骤、来源与消耗' },
      { name: 'admin-runs', label: '调用记录', icon: Activity, desc: '每一次智能体模型调用：耗时、token、费用与错误', keywords: 'token 费用 错误 失败' },
    ],
  },
  {
    group: '账号',
    items: [{ name: 'admin-users', label: '用户', icon: Users, desc: '账号、管理员权限与停用', keywords: '管理员 停用' }],
  },
]

export const ADMIN_ITEMS = ADMIN_NAV.flatMap((g) => g.items.map((it) => ({ ...it, group: g.group })))
export const ADMIN_ICON_FALLBACK = Boxes

export function findAdminItem(name: unknown) {
  return ADMIN_ITEMS.find((i) => i.name === name) ?? null
}
