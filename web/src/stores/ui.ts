import { defineStore } from 'pinia'

/** 跨组件的界面状态（如历史抽屉），不涉及任何后端操作 */
export const useUiStore = defineStore('ui', {
  state: () => ({ historyOpen: false }),
  actions: {
    openHistory() {
      this.historyOpen = true
    },
    closeHistory() {
      this.historyOpen = false
    },
  },
})
