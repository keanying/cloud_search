import { defineStore } from 'pinia'

/** 跨组件的界面状态（历史抽屉、对话侧栏、首页落地页滚动状态），不涉及任何后端操作 */
export const useUiStore = defineStore('ui', {
  state: () => ({
    historyOpen: false,
    /** 宽屏：左侧对话列表是否收起（保存在本浏览器） */
    sidebarCollapsed: localStorage.getItem('cs_sidebar_collapsed') === '1',
    /** 窄屏：对话列表抽屉 */
    sidebarDrawer: false,
    /** 窄屏：本次任务抽屉 */
    dashboardDrawer: false,
    /** 最近打开的对话（顶栏“对话”入口） */
    lastChatId: localStorage.getItem('cs_last_chat') as string | null,
    /** 首页：已滚动离开首屏（顶栏变为不透明） */
    landingScrolled: false,
    /** 首页：当前可见的介绍区块 id（顶栏导航高亮） */
    activeSection: '' as string,
  }),
  actions: {
    openHistory() {
      this.historyOpen = true
    },
    closeHistory() {
      this.historyOpen = false
    },
    setLastChat(id: string | null) {
      this.lastChatId = id
      if (id) localStorage.setItem('cs_last_chat', id)
      else localStorage.removeItem('cs_last_chat')
    },
    setSidebarCollapsed(v: boolean) {
      this.sidebarCollapsed = v
      localStorage.setItem('cs_sidebar_collapsed', v ? '1' : '0')
    },
  },
})
