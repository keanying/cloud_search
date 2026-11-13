<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { AlertTriangle, Globe, Hand, Info, Loader2, Lock, MousePointerClick, Radio, RefreshCw, SkipForward, WifiOff } from 'lucide-vue-next'
import type { BrowserSessionOut, HandoffState, ViewerMetaOut } from '@/api/types'
import { api, ApiError } from '@/api/client'
import { formatTime, taskStatusLabel } from '@/lib/format'
import { useLiveView } from '@/lib/useLiveView'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'
import EmptyState from '@/components/common/EmptyState.vue'

/**
 * 云端浏览器阅览：优先实时画面（WebSocket），不可用时回退定期截图。
 * 默认只读；只有在任务请求人工协助（如人机验证）且用户点击“接手处理”、服务端确认 interactive 后才转发输入。
 * 打开/切换/刷新/关闭本面板都不会启动、刷新源网页或停止任务。
 */
const props = defineProps<{ taskId: string | null }>()
const panel = usePanelStore()
const toast = useToastStore()

const sessions = ref<BrowserSessionOut[]>([])
const sessionsLoaded = ref(false)
const meta = ref<ViewerMetaOut | null>(null)
const metaError = ref<string | null>(null)
const snapUrl = ref<string | null>(null)
const frameSeq = ref<number>(-1)
const noFrame = ref(false)
const lastPollOk = ref<number>(0)
const now = ref(Date.now())
const actionBusy = ref(false)

let metaTimer: number | undefined
let listTimer: number | undefined
let clockTimer: number | undefined

const selectedId = computed({
  get: () => panel.browserSessionId,
  set: (v) => (panel.browserSessionId = v),
})

const selectedSession = computed(() => sessions.value.find((s) => s.browser_session_id === selectedId.value) ?? null)
const sessionActive = computed(() => (meta.value?.session_status ?? selectedSession.value?.session_status) === 'active')
const liveEnabled = computed(
  () => !!selectedId.value && sessionActive.value && (meta.value?.live_available ?? selectedSession.value?.live_available ?? true) !== false,
)
const live = useLiveView(selectedId, liveEnabled)
const isLive = computed(() => live.connected.value && !!live.frameSrc.value)

const handoffState = computed<HandoffState>(
  () => live.status.value?.handoff_state ?? meta.value?.handoff_state ?? selectedSession.value?.handoff_state ?? 'none',
)
const handoffReason = computed(() => live.status.value?.handoff_reason ?? meta.value?.handoff_reason ?? null)
const handoffDeadline = computed(() => live.status.value?.handoff_deadline ?? meta.value?.handoff_deadline ?? null)
/** 选中会话以实时状态为准，其余用列表数据 */
function tabHandoff(s: BrowserSessionOut): HandoffState {
  return s.browser_session_id === selectedId.value ? handoffState.value : (s.handoff_state ?? 'none')
}
const interactive = computed(() => isLive.value && !!live.status.value?.interactive)
const countdown = computed(() => {
  if (!handoffDeadline.value) return null
  const d = handoffDeadline.value
  const t = new Date(d.endsWith('Z') || d.includes('+') ? d : d + 'Z').getTime()
  const s = Math.max(0, Math.round((t - now.value) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})

async function loadSessions() {
  if (!props.taskId) return
  try {
    const list = await api.taskBrowserSessions(props.taskId)
    sessions.value = list
    sessionsLoaded.value = true
    const want = panel.browserSessionId
    if (!want || !list.some((s) => s.browser_session_id === want)) {
      const pick =
        list.find((s) => s.handoff_state === 'requested' || s.handoff_state === 'active') ??
        list.find((s) => s.session_status === 'active') ??
        list[list.length - 1]
      selectedId.value = pick?.browser_session_id ?? null
    }
  } catch {
    sessionsLoaded.value = true
  }
}

function setSnap(blob: Blob | null) {
  if (snapUrl.value) URL.revokeObjectURL(snapUrl.value)
  snapUrl.value = blob ? URL.createObjectURL(blob) : null
}

async function pollMeta() {
  const id = selectedId.value
  if (!id || document.hidden) return
  try {
    const m = await api.viewerMeta(id)
    if (selectedId.value !== id) return
    meta.value = m
    metaError.value = null
    lastPollOk.value = Date.now()
    // 实时画面可用时不拉截图；否则帧序号变化才重新取图
    if (isLive.value) return
    if (m.frame_seq_no !== frameSeq.value && m.frame_seq_no > 0 && !m.masked) {
      const blob = await api.viewerSnapshot(id)
      if (selectedId.value !== id) return
      if (blob) {
        setSnap(blob)
        frameSeq.value = m.frame_seq_no
        noFrame.value = false
      } else noFrame.value = true
    } else if (m.frame_seq_no <= 0) {
      noFrame.value = true
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 410) metaError.value = '该浏览器会话已结束，无法继续阅览'
    else if (e instanceof ApiError && e.status === 404) metaError.value = '会话不存在或无权访问'
    else metaError.value = '阅览连接中断，正在重试…'
  }
}

/** 刷新阅览：只重新读取最近画面 / 重连实时画面，不刷新来源网页 */
async function refreshView() {
  frameSeq.value = -1
  if (liveEnabled.value && !live.connected.value) void live.reconnect()
  await pollMeta()
}

function start() {
  stop()
  void loadSessions().then(pollMeta)
  metaTimer = window.setInterval(pollMeta, 2000)
  listTimer = window.setInterval(loadSessions, 6000)
  clockTimer = window.setInterval(() => (now.value = Date.now()), 1000)
}
function stop() {
  window.clearInterval(metaTimer)
  window.clearInterval(listTimer)
  window.clearInterval(clockTimer)
}

watch(
  () => props.taskId,
  () => {
    sessions.value = []
    sessionsLoaded.value = false
    meta.value = null
    frameSeq.value = -1
    setSnap(null)
    start()
  },
  { immediate: true },
)
watch(selectedId, () => {
  meta.value = null
  frameSeq.value = -1
  noFrame.value = false
  setSnap(null)
  void pollMeta()
})
onBeforeUnmount(() => {
  stop()
  setSnap(null)
})

const disconnected = computed(
  () => !isLive.value && (!!metaError.value || (lastPollOk.value > 0 && now.value - lastPollOk.value > 8000)),
)
const ended = computed(() => meta.value && ['closed', 'lost', 'closing'].includes(meta.value.session_status))
const frameAge = computed(() => {
  if (!meta.value?.frame_time) return null
  const t = new Date(meta.value.frame_time.endsWith('Z') ? meta.value.frame_time : meta.value.frame_time + 'Z').getTime()
  return Math.max(0, Math.round((now.value - t) / 1000))
})
const shownUrl = computed(() => (isLive.value && live.frameUrl.value) || meta.value?.current_url || '')
const shownTitle = computed(() => (isLive.value && live.frameTitle.value) || meta.value?.current_title || '')

// ---------------------------------------------------------------- 人工接手
async function takeOver() {
  const id = selectedId.value
  if (!id) return
  actionBusy.value = true
  try {
    meta.value = await api.takeover(id)
    panel.interactiveSessionId = id
    if (!live.connected.value) void live.reconnect()
    setTimeout(() => keyTarget.value?.focus(), 200)
  } catch (e) {
    toast.error(e, '接手失败')
  } finally {
    actionBusy.value = false
  }
}

async function giveBack(resolved: boolean) {
  const id = selectedId.value
  if (!id) return
  actionBusy.value = true
  try {
    meta.value = await api.takeoverReturn(id, resolved)
    panel.interactiveSessionId = null
    toast.push(resolved ? '已交还给 AI，任务继续' : '已跳过，AI 将尝试其他来源', 'info')
  } catch (e) {
    toast.error(e, '操作失败')
  } finally {
    actionBusy.value = false
  }
}

// ---------------------------------------------------------------- 输入转发（仅 interactive 时）
const frameImg = ref<HTMLImageElement | null>(null)
const keyTarget = ref<HTMLTextAreaElement | null>(null)
const composing = ref(false)
let lastMove = 0

function toPage(e: MouseEvent | WheelEvent): { x: number; y: number } | null {
  const img = frameImg.value
  if (!img) return null
  const r = img.getBoundingClientRect()
  if (!r.width || !r.height) return null
  const fx = Math.min(Math.max(e.clientX - r.left, 0), r.width)
  const fy = Math.min(Math.max(e.clientY - r.top, 0), r.height)
  return {
    x: Math.round((fx / r.width) * live.frameSize.value.width),
    y: Math.round((fy / r.height) * live.frameSize.value.height),
  }
}

const BUTTONS = ['left', 'middle', 'right'] as const

function onPointer(e: PointerEvent, action: 'move' | 'down' | 'up') {
  if (!interactive.value) return
  if (action === 'move') {
    const t = performance.now()
    if (t - lastMove < 50) return // 约 20 次/秒
    lastMove = t
  } else {
    e.preventDefault()
    keyTarget.value?.focus()
  }
  const p = toPage(e)
  if (!p) return
  live.send({
    type: 'mouse',
    action,
    x: p.x,
    y: p.y,
    button: BUTTONS[e.button] ?? 'left',
    clickCount: action === 'move' ? 0 : Math.max(1, e.detail || 1),
    deltaX: 0,
    deltaY: 0,
  })
}

function onWheel(e: WheelEvent) {
  if (!interactive.value) return
  e.preventDefault()
  const p = toPage(e)
  if (!p) return
  live.send({ type: 'mouse', action: 'wheel', x: p.x, y: p.y, button: 'left', clickCount: 0, deltaX: e.deltaX, deltaY: e.deltaY })
}

function onKey(e: KeyboardEvent, action: 'down' | 'up') {
  if (!interactive.value) return
  // 输入法组合输入期间不转发按键，组合结束后以 text 发送
  if (e.isComposing || composing.value || e.keyCode === 229) return
  // 允许粘贴快捷键交给 paste 事件处理
  if (action === 'down' && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') return
  e.preventDefault()
  const printable = e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey
  live.send({ type: 'key', action, key: e.key, code: e.code, text: action === 'down' && printable ? e.key : null })
}

function onCompositionEnd(e: CompositionEvent) {
  composing.value = false
  if (interactive.value && e.data) live.send({ type: 'text', text: e.data })
  if (keyTarget.value) keyTarget.value.value = ''
}

function onPaste(e: ClipboardEvent) {
  if (!interactive.value) return
  e.preventDefault()
  const t = e.clipboardData?.getData('text/plain')
  if (t) live.send({ type: 'text', text: t })
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 会话标签：切换只改变查看对象，不改变执行 Owner -->
    <div v-if="sessions.length" class="hairline flex gap-1 overflow-x-auto border-b px-3 pt-2" role="tablist" aria-label="浏览器会话">
      <button
        v-for="s in sessions"
        :key="s.browser_session_id"
        role="tab"
        :aria-selected="s.browser_session_id === selectedId"
        class="flex shrink-0 items-center gap-1.5 rounded-t-lg border border-b-0 px-3 py-1.5 text-xs"
        :class="s.browser_session_id === selectedId ? 'hairline bg-white/5 text-white' : 'border-transparent text-slate-400 hover:text-white'"
        @click="selectedId = s.browser_session_id"
      >
        <span
          class="h-1.5 w-1.5 rounded-full"
          :class="tabHandoff(s) === 'requested' ? 'animate-pulse bg-amber-500' : s.session_status === 'active' ? 'bg-emerald-500' : 'bg-slate-500'"
        />
        {{ s.session_label }}
        <span v-if="tabHandoff(s) === 'requested'" class="text-amber-300">· 需要人工处理</span>
        <span v-else-if="tabHandoff(s) === 'active'" class="text-brand-300">· 人工操作中</span>
      </button>
    </div>

    <!-- 人工协助请求 / 进行中 -->
    <div
      v-if="selectedId && handoffState === 'requested' && !interactive"
      class="mx-3 mt-3 flex items-center gap-3 rounded-xl border border-amber-400/40 bg-amber-500/10 px-3 py-2.5"
      role="alert"
    >
      <span class="relative flex h-2.5 w-2.5 shrink-0">
        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75 motion-reduce:animate-none" />
        <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-500" />
      </span>
      <div class="min-w-0 flex-1 text-sm">
        <div class="font-medium text-amber-200">需要人工处理</div>
        <div class="truncate text-xs text-slate-300">{{ handoffReason || '页面需要你协助完成验证' }}<template v-if="countdown"> · 剩余 {{ countdown }}</template></div>
      </div>
      <button class="btn-primary btn-sm" :disabled="actionBusy" @click="takeOver"><Hand class="h-3.5 w-3.5" /> 接手处理</button>
      <button class="btn-ghost btn-sm" :disabled="actionBusy" @click="giveBack(false)"><SkipForward class="h-3.5 w-3.5" /> 跳过</button>
    </div>
    <div
      v-if="interactive"
      class="mx-3 mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-violet-500 px-3 py-2 text-snow shadow-md"
      role="status"
    >
      <MousePointerClick class="h-4 w-4" />
      <span class="text-sm font-medium">你正在操作云端浏览器 · AI 已暂停</span>
      <span v-if="countdown" class="text-xs opacity-80">剩余 {{ countdown }}</span>
      <div class="flex-1" />
      <button class="btn btn-sm bg-snow/95 text-[#4f46e5] hover:bg-snow" :disabled="actionBusy" @click="giveBack(true)">
        <Loader2 v-if="actionBusy" class="h-3.5 w-3.5 animate-spin" /> 完成，交还给 AI
      </button>
      <button class="btn btn-sm text-snow/90 hover:bg-snow/15" :disabled="actionBusy" @click="giveBack(false)">跳过</button>
    </div>

    <div class="min-h-0 flex-1 overflow-auto p-3">
      <EmptyState
        v-if="sessionsLoaded && !sessions.length"
        title="当前任务尚未启动浏览器"
        desc="浏览器由后台根据任务需要自动启动；打开阅览不会启动采集"
      />
      <template v-else-if="selectedId">
        <div
          class="relative overflow-hidden rounded-xl border bg-ink-800"
          :class="interactive ? 'border-brand-500 ring-2 ring-brand-400/50' : 'hairline'"
        >
          <!-- 实时画面 -->
          <img
            v-if="isLive && !meta?.masked"
            ref="frameImg"
            :src="live.frameSrc.value || ''"
            alt="云端浏览器实时画面"
            class="block w-full select-none"
            :class="interactive ? 'cursor-crosshair' : ''"
            draggable="false"
            @pointermove="onPointer($event, 'move')"
            @pointerdown="onPointer($event, 'down')"
            @pointerup="onPointer($event, 'up')"
            @wheel="onWheel"
            @contextmenu.prevent
          />
          <!-- 定期截图 -->
          <img
            v-else-if="snapUrl && !meta?.masked"
            :src="snapUrl"
            alt="云端浏览器最近画面截图"
            class="block w-full"
            :class="meta?.stale || ended ? 'opacity-60' : ''"
          />
          <div v-else-if="meta?.masked" class="flex aspect-video flex-col items-center justify-center gap-2 text-sm text-slate-400">
            <Lock class="h-6 w-6" /> 该页面因隐私策略不提供画面
          </div>
          <div v-else class="flex aspect-video items-center justify-center text-sm text-slate-500">
            {{ noFrame ? '暂无画面帧' : '正在获取画面…' }}
          </div>
          <div v-if="!isLive && (meta?.stale || ended)" class="absolute top-2 left-2 rounded-md bg-amber-500/90 px-2 py-0.5 text-xs font-medium text-black">
            {{ ended ? '会话已结束 · 最后一帧' : '画面已过期' }}
          </div>
          <!-- 键盘与输入法：可聚焦的隐藏输入框，仅在可交互时转发 -->
          <textarea
            v-if="interactive"
            ref="keyTarget"
            class="absolute h-px w-px opacity-0"
            aria-label="向云端浏览器输入（按键、输入法与粘贴会发送到页面）"
            @keydown="onKey($event, 'down')"
            @keyup="onKey($event, 'up')"
            @compositionstart="composing = true"
            @compositionend="onCompositionEnd"
            @paste="onPaste"
          />
        </div>
        <p v-if="interactive" class="mt-2 text-xs text-slate-400">
          点击画面后即可操作：鼠标、滚轮、键盘与输入法都会发送到云端页面。密码不会被记录或发送给 AI。
        </p>

        <div v-if="metaError || disconnected" class="mt-2 flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          <WifiOff class="h-4 w-4" /> {{ metaError || '阅览断连，云任务仍在后台运行' }}
        </div>

        <dl v-if="meta || isLive" class="mt-3 space-y-1.5 text-xs">
          <div class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">当前地址</dt>
            <dd class="min-w-0 flex-1 truncate font-mono text-slate-300" :title="shownUrl">{{ shownUrl || '—' }}</dd>
          </div>
          <div v-if="shownTitle" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">页面标题</dt>
            <dd class="min-w-0 flex-1 truncate text-slate-300">{{ shownTitle }}</dd>
          </div>
          <div v-if="meta?.current_activity" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">正在</dt>
            <dd class="text-slate-300">{{ meta.current_activity }}</dd>
          </div>
          <div v-if="meta" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">任务状态</dt>
            <dd class="text-slate-300">{{ taskStatusLabel(meta.task_status) }}</dd>
          </div>
        </dl>
      </template>
    </div>

    <footer class="hairline flex flex-wrap items-center gap-x-3 gap-y-1 border-t px-3 py-2 text-xs text-slate-400">
      <span v-if="isLive" class="flex items-center gap-1 font-medium text-emerald-300"><Radio class="h-3.5 w-3.5" /> 实时</span>
      <span v-else class="flex items-center gap-1"><Info class="h-3.5 w-3.5" /> 定期截图 · 非实时</span>
      <span v-if="!isLive && meta?.frame_time">帧时间 {{ formatTime(meta.frame_time) }}<template v-if="frameAge != null">（{{ frameAge }} 秒前）</template></span>
      <span v-if="meta && !meta.connected && !isLive" class="flex items-center gap-1 text-amber-300"><AlertTriangle class="h-3.5 w-3.5" /> 浏览器未连接</span>
      <div class="flex-1" />
      <button v-if="selectedId" class="flex items-center gap-1 hover:text-white" title="只重新读取画面，不刷新来源网页" @click="refreshView">
        <RefreshCw class="h-3.5 w-3.5" /> 刷新阅览
      </button>
      <span class="flex items-center gap-1"><Globe class="h-3.5 w-3.5" /> 关闭阅览不停止后台任务</span>
    </footer>
  </div>
</template>
