// 云端浏览器实时画面（WebSocket）。失败时由调用方回退到定期截图；带退避重连。
import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { HandoffState, LiveClientMsg, LiveServerMsg } from '@/api/types'
import { api, ApiError } from '@/api/client'

export interface LiveStatus {
  session_status: string
  handoff_state: HandoffState
  handoff_reason: string | null
  handoff_deadline: string | null
  interactive: boolean
}

export function useLiveView(sessionId: Ref<string | null>, enabled: Ref<boolean>) {
  const connected = ref(false)
  /** live 不可用（409/404 或多次失败）：调用方显示定期截图 */
  const unavailable = ref(false)
  const frameSrc = ref<string | null>(null)
  const frameSize = ref<{ width: number; height: number }>({ width: 1280, height: 860 })
  const frameUrl = ref<string>('')
  const frameTitle = ref<string>('')
  const lastFrameAt = ref<number>(0)
  const status = ref<LiveStatus | null>(null)
  const error = ref<string | null>(null)

  let ws: WebSocket | null = null
  let retry = 0
  let retryTimer: number | undefined
  let closedByUs = false
  let generation = 0

  function cleanup() {
    window.clearTimeout(retryTimer)
    if (ws) {
      closedByUs = true
      try {
        ws.close()
      } catch {
        /* ignore */
      }
    }
    ws = null
    connected.value = false
  }

  async function connect() {
    cleanup()
    const id = sessionId.value
    if (!id || !enabled.value) return
    const gen = ++generation
    closedByUs = false
    try {
      const t = await api.liveTicket(id)
      if (gen !== generation) return
      const sock = new WebSocket(api.liveUrl(id, t.ticket))
      ws = sock
      sock.onopen = () => {
        if (gen !== generation) return
        connected.value = true
        unavailable.value = false
        error.value = null
        retry = 0
      }
      sock.onmessage = (ev) => {
        if (gen !== generation) return
        let msg: LiveServerMsg
        try {
          msg = JSON.parse(ev.data as string)
        } catch {
          return
        }
        if (msg.type === 'frame') {
          frameSrc.value = `data:image/jpeg;base64,${msg.data}`
          frameSize.value = { width: msg.width || 1280, height: msg.height || 860 }
          frameUrl.value = msg.url || ''
          frameTitle.value = msg.title || ''
          lastFrameAt.value = Date.now()
        } else if (msg.type === 'status') {
          status.value = {
            session_status: msg.session_status,
            handoff_state: msg.handoff_state,
            handoff_reason: msg.handoff_reason,
            handoff_deadline: msg.handoff_deadline,
            interactive: !!msg.interactive,
          }
        } else if (msg.type === 'error') {
          error.value = msg.message
        }
      }
      sock.onclose = () => {
        if (gen !== generation) return
        connected.value = false
        if (closedByUs) return
        scheduleRetry()
      }
      sock.onerror = () => {
        /* onclose 会接着触发 */
      }
    } catch (e) {
      if (gen !== generation) return
      if (e instanceof ApiError && (e.status === 409 || e.status === 404 || e.status === 410)) {
        unavailable.value = true
        return
      }
      scheduleRetry()
    }
  }

  function scheduleRetry() {
    retry += 1
    if (retry >= 4) unavailable.value = true // 期间显示截图，但仍继续尝试
    const delay = Math.min(15000, 1000 * 2 ** Math.min(retry, 4))
    retryTimer = window.setTimeout(() => void connect(), delay)
  }

  /** 只在服务端确认可交互时发送输入 */
  function send(msg: LiveClientMsg) {
    if (!ws || ws.readyState !== WebSocket.OPEN || !status.value?.interactive) return
    ws.send(JSON.stringify(msg))
  }

  watch([sessionId, enabled], () => {
    frameSrc.value = null
    status.value = null
    unavailable.value = false
    retry = 0
    if (enabled.value && sessionId.value) void connect()
    else cleanup()
  }, { immediate: true })

  onBeforeUnmount(() => {
    generation++
    cleanup()
  })

  return { connected, unavailable, frameSrc, frameSize, frameUrl, frameTitle, lastFrameAt, status, error, send, reconnect: connect }
}
