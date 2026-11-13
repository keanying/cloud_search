import { defineStore } from 'pinia'

/** 跨组件的界面状态（如历史抽屉、首页落地页的滚动状态），不涉及任何后端操作 */
export const useUiStore = defineStore('ui', {
  state: () => ({
    historyOpen: false,
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
  },
})
