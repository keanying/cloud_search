// 当前打开会话的状态：消息、任务、事件水位、SSE 连接与“停止当前轮”。
import { defineStore } from 'pinia'
import { api } from '@/api/client'
import { openConversationStream } from '@/api/sse'
import type { ConversationOut, FileOut, MessageOut, ModeSelection, TaskOut } from '@/api/types'
import { ACTIVE_STATUSES } from '@/lib/format'
import { useConversationsStore } from './conversations'

let streamStop: (() => void) | null = null

type StreamStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

function newClientId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversationId: null as string | null,
    conversation: null as ConversationOut | null,
    messages: [] as MessageOut[],
    tasks: {} as Record<string, TaskOut>,
    /** 本对话上传的文件（含尚未发送的附件），由 file_updated 事件实时更新 */
    files: {} as Record<string, FileOut>,
    lastSeq: 0,
    loading: false,
    loadError: null as string | null,
    sending: false,
    streamStatus: 'idle' as StreamStatus,
    /** 已发出停止命令、等待后端确认的任务 */
    stoppingTaskIds: [] as string[],
    stopRequestedAt: 0,
  }),
  getters: {
    activeTasks(s): TaskOut[] {
      return Object.values(s.tasks).filter((t) => ACTIVE_STATUSES.has(t.task_status))
    },
    hasActive(): boolean {
      return this.activeTasks.length > 0
    },
    /** 后端确认前一直显示“正在停止…” */
    isStopping(s): boolean {
      return s.stoppingTaskIds.some((id) => {
        const t = s.tasks[id]
        return !t || ACTIVE_STATUSES.has(t.task_status)
      })
    },
    /** 已随消息发送的文件（“对话中的文件”） */
    sentFiles(s): FileOut[] {
      return Object.values(s.files)
        .filter((f) => f.message_id)
        .sort((a, b) => ((a.created_time || '') < (b.created_time || '') ? -1 : 1))
    },
    lastTurnId(s): string | null {
      for (let i = s.messages.length - 1; i >= 0; i--) {
        if (s.messages[i].role === 'user') return s.messages[i].turn_id
      }
      return null
    },
  },
  actions: {
    async open(id: string) {
      if (this.conversationId === id && this.streamStatus !== 'idle' && this.streamStatus !== 'closed') return
      this.close()
      this.$patch({
        conversationId: id,
        conversation: null,
        messages: [],
        tasks: {},
        files: {},
        lastSeq: 0,
        loadError: null,
        stoppingTaskIds: [],
      })
      this.loading = true
      try {
        const [conv, msgs, tasks, files] = await Promise.all([
          api.getConversation(id),
          api.listMessages(id),
          api.conversationTasks(id).catch(() => [] as TaskOut[]),
          api.listFiles(id).catch(() => [] as FileOut[]),
        ])
        if (this.conversationId !== id) return
        this.conversation = conv
        this.messages = msgs.items
        this.lastSeq = msgs.last_event_seq_no
        for (const t of tasks) this.tasks[t.task_id] = t
        for (const f of files) this.files[f.file_id] = f
      } catch (e) {
        this.loadError = e instanceof Error ? e.message : '加载失败'
        this.loading = false
        return
      }
      this.loading = false
      this.connect()
    },

    connect() {
      if (!this.conversationId) return
      const id = this.conversationId
      this._stopStream()
      const stop = openConversationStream({
        conversationId: id,
        afterSeq: this.lastSeq,
        onEvent: (type, data, seq) => {
          if (this.conversationId !== id) return
          if (seq > this.lastSeq) this.lastSeq = seq
          this.handleEvent(type, data)
        },
        onReconnect: () => {
          void this.resync()
        },
        onStatus: (s) => {
          if (this.conversationId === id) this.streamStatus = s
        },
      })
      streamStop = stop
    },

    _stopStream() {
      streamStop?.()
      streamStop = null
    },

    close() {
      this._stopStream()
      this.streamStatus = 'idle'
      this.conversationId = null
    },

    /** 重连后从持久快照追赶，不重放任何命令 */
    async resync() {
      const id = this.conversationId
      if (!id) return
      try {
        const [msgs, tasks, files] = await Promise.all([
          api.listMessages(id),
          api.conversationTasks(id),
          api.listFiles(id).catch(() => [] as FileOut[]),
        ])
        if (this.conversationId !== id) return
        this.messages = msgs.items
        for (const f of files) this.files[f.file_id] = f
        if (msgs.last_event_seq_no > this.lastSeq) this.lastSeq = msgs.last_event_seq_no
        for (const t of tasks) this.tasks[t.task_id] = t
      } catch {
        /* 下次重连再试 */
      }
    },

    upsertMessage(m: MessageOut) {
      const i = this.messages.findIndex((x) => x.message_id === m.message_id)
      if (i >= 0) {
        // 旧事件不回退较新的版本
        if (this.messages[i].updated_time > m.updated_time) return
        this.messages[i] = m
      } else {
        this.messages.push(m)
        this.messages.sort((a, b) => (a.created_time < b.created_time ? -1 : a.created_time > b.created_time ? 1 : 0))
      }
      const unknown = m.task_ids.filter((t) => !this.tasks[t])
      if (unknown.length) void this.refreshTasks()
    },

    upsertTask(t: TaskOut) {
      const cur = this.tasks[t.task_id]
      if (cur && cur.updated_time > t.updated_time) return
      this.tasks[t.task_id] = t
    },

    async refreshTasks() {
      const id = this.conversationId
      if (!id) return
      try {
        const tasks = await api.conversationTasks(id)
        if (this.conversationId !== id) return
        for (const t of tasks) this.upsertTask(t)
      } catch {
        /* ignore */
      }
    },

    async refreshTask(taskId: string) {
      try {
        this.upsertTask(await api.getTask(taskId))
      } catch {
        /* ignore */
      }
    },

    handleEvent(type: string, data: unknown) {
      if (!data || typeof data !== 'object') return
      switch (type) {
        case 'message_created':
        case 'message_updated':
          this.upsertMessage(data as MessageOut)
          break
        case 'task_updated':
          this.upsertTask(data as TaskOut)
          break
        case 'file_updated': {
          const f = data as FileOut
          this.files[f.file_id] = f
          break
        }
        case 'conversation_updated': {
          const c = data as ConversationOut
          this.conversation = c
          useConversationsStore().upsert(c)
          break
        }
      }
    },

    async send(text: string, mode: ModeSelection, fileIds: string[] = []) {
      const id = this.conversationId
      if (!id || this.sending) return
      this.sending = true
      try {
        const res = await api.sendMessage(id, {
          client_message_id: newClientId(),
          text,
          mode_selection: mode,
          ...(fileIds.length ? { file_ids: fileIds } : {}),
        })
        if (this.conversationId === id) {
          this.upsertMessage(res.user_message)
          this.upsertMessage(res.assistant_message)
          for (const fid of fileIds) {
            const f = this.files[fid]
            if (f) this.files[fid] = { ...f, message_id: res.user_message.message_id }
          }
        }
        return res
      } finally {
        this.sending = false
      }
    },

    async stopTurn() {
      const id = this.conversationId
      if (!id) return
      const res = await api.stopTurn(id, this.lastTurnId)
      const accepted = res.results.filter((r) => r.outcome === 'accepted').map((r) => r.task_id)
      // 当前轮之外仍在运行的任务不受影响；只追踪本次真正被接受停止的任务
      this.stoppingTaskIds = accepted
      this.stopRequestedAt = Date.now()
      for (const tid of accepted) void this.refreshTask(tid)
      return res
    },
  },
})
