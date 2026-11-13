// 会话事件流：Bearer 鉴权 + Last-Event-ID 续传 + 指数退避重连。
import { fetchEventSource, type EventSourceMessage } from '@microsoft/fetch-event-source'
import { API_BASE, authHeaders } from './client'

class RetriableError extends Error {}
class FatalError extends Error {}

export interface ConversationStreamOptions {
  conversationId: string
  /** 起始水位：只接收 seq 更大的事件 */
  afterSeq: number
  onEvent: (type: string, data: unknown, seq: number) => void
  /** 非首次连接成功（重连）时回调，用于重新拉取消息快照 */
  onReconnect?: () => void
  onStatus?: (status: 'connecting' | 'open' | 'reconnecting' | 'closed') => void
}

export function openConversationStream(opts: ConversationStreamOptions): () => void {
  const ctrl = new AbortController()
  let lastSeq = opts.afterSeq
  let opened = false
  let attempt = 0

  opts.onStatus?.('connecting')
  const headers = authHeaders({ Accept: 'text/event-stream' })
  if (lastSeq > 0) headers['Last-Event-ID'] = String(lastSeq)

  fetchEventSource(`${API_BASE}/conversations/${encodeURIComponent(opts.conversationId)}/events?after=${lastSeq}`, {
    headers,
    signal: ctrl.signal,
    openWhenHidden: true,
    async onopen(res) {
      const ct = res.headers.get('content-type') || ''
      if (res.ok && ct.includes('text/event-stream')) {
        attempt = 0
        opts.onStatus?.('open')
        if (opened) opts.onReconnect?.()
        opened = true
        return
      }
      if (res.status === 401 || res.status === 403 || res.status === 404) {
        throw new FatalError(`stream ${res.status}`)
      }
      throw new RetriableError(`stream ${res.status}`)
    },
    onmessage(msg: EventSourceMessage) {
      if (!msg.event && !msg.data) return
      const seq = Number(msg.id)
      if (Number.isFinite(seq) && seq > 0) {
        if (seq <= lastSeq) return // 去重
        lastSeq = seq
      }
      let data: unknown = null
      try {
        data = msg.data ? JSON.parse(msg.data) : null
      } catch {
        return
      }
      opts.onEvent(msg.event || 'message', data, seq)
    },
    onclose() {
      // 服务端正常关闭也重连
      throw new RetriableError('closed')
    },
    onerror(err) {
      if (err instanceof FatalError || ctrl.signal.aborted) {
        opts.onStatus?.('closed')
        throw err
      }
      attempt += 1
      opts.onStatus?.('reconnecting')
      const base = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5))
      return base / 2 + Math.random() * (base / 2)
    },
  }).catch(() => {
    /* fatal 或已中止 */
  })

  return () => ctrl.abort()
}
