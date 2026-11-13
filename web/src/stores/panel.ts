import { defineStore } from 'pinia'

export type PanelType = 'browser' | 'sources' | 'artifact'

/** 右侧面板只改变展示内容；开关/切换不调用任何影响任务执行的接口 */
export const usePanelStore = defineStore('panel', {
  state: () => ({
    open: false,
    type: 'browser' as PanelType,
    taskId: null as string | null,
    focusN: null as number | null,
    artifactId: null as string | null,
    browserSessionId: null as string | null,
    widthPct: 40,
  }),
  actions: {
    openBrowser(taskId: string) {
      this.type = 'browser'
      this.taskId = taskId
      this.open = true
    },
    openSources(taskId: string, focusN: number | null = null) {
      this.type = 'sources'
      this.taskId = taskId
      this.focusN = focusN
      this.open = true
    },
    openArtifact(artifactId: string, taskId: string | null = null) {
      this.type = 'artifact'
      this.artifactId = artifactId
      if (taskId) this.taskId = taskId
      this.open = true
    },
    setType(t: PanelType) {
      this.type = t
    },
    close() {
      this.open = false
    },
    reset() {
      this.open = false
      this.taskId = null
      this.focusN = null
      this.artifactId = null
      this.browserSessionId = null
    },
  },
})
