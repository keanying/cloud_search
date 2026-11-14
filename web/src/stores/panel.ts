import { defineStore } from 'pinia'
import type { ArtifactFormat } from '@/api/types'

export type PanelType = 'browser' | 'sources' | 'artifact' | 'file'

/** 右侧面板只改变展示内容；开关/切换不调用任何影响任务执行的接口 */
export const usePanelStore = defineStore('panel', {
  state: () => ({
    open: false,
    type: 'browser' as PanelType,
    taskId: null as string | null,
    focusN: null as number | null,
    artifactId: null as string | null,
    /** 当前成果的其他格式（用于面板内下载按钮） */
    artifactFormats: [] as ArtifactFormat[],
    artifactName: null as string | null,
    browserSessionId: null as string | null,
    /** 文件预览（上传的文件） */
    fileId: null as string | null,
    /** 请求以“人工接手”模式查看该会话（实际是否可操作以服务端 interactive 为准） */
    interactiveSessionId: null as string | null,
    widthPct: 40,
    /** 用户在某任务运行期间手动关闭过面板：同一任务不再自动弹出 */
    dismissedTaskIds: [] as string[],
    /** 已经自动弹出过的任务 */
    autoOpenedTaskIds: [] as string[],
  }),
  actions: {
    openBrowser(taskId: string, sessionId: string | null = null) {
      this.type = 'browser'
      this.taskId = taskId
      if (sessionId) this.browserSessionId = sessionId
      this.open = true
    },
    /** 自动弹出：受设置控制，且同一任务被用户关闭后不再弹出 */
    autoOpenBrowser(taskId: string, sessionId: string | null = null): boolean {
      if (this.dismissedTaskIds.includes(taskId)) return false
      if (this.open && this.type === 'browser' && this.taskId === taskId) return false
      this.openBrowser(taskId, sessionId)
      if (!this.autoOpenedTaskIds.includes(taskId)) this.autoOpenedTaskIds.push(taskId)
      return true
    },
    openSources(taskId: string, focusN: number | null = null) {
      this.type = 'sources'
      this.taskId = taskId
      this.focusN = focusN
      this.open = true
    },
    openArtifact(artifactId: string, taskId: string | null = null, formats: ArtifactFormat[] = [], name: string | null = null) {
      this.type = 'artifact'
      this.artifactId = artifactId
      this.artifactFormats = formats
      this.artifactName = name
      if (taskId) this.taskId = taskId
      // 报告预览更宽
      if (formats.some((f) => f.format === 'html')) this.widthPct = Math.max(this.widthPct, 50)
      this.open = true
    },
    openFile(fileId: string) {
      this.type = 'file'
      this.fileId = fileId
      this.widthPct = Math.max(this.widthPct, 45)
      this.open = true
    },
    setType(t: PanelType) {
      this.type = t
    },
    close() {
      if (this.open && this.type === 'browser' && this.taskId && !this.dismissedTaskIds.includes(this.taskId)) {
        this.dismissedTaskIds.push(this.taskId)
      }
      this.open = false
    },
    reset() {
      this.open = false
      this.taskId = null
      this.focusN = null
      this.artifactId = null
      this.artifactFormats = []
      this.artifactName = null
      this.fileId = null
      this.browserSessionId = null
      this.interactiveSessionId = null
      this.dismissedTaskIds = []
      this.autoOpenedTaskIds = []
    },
  },
})
