<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { AlertTriangle, Globe, Info, Lock, RefreshCw, WifiOff } from 'lucide-vue-next'
import type { BrowserSessionOut, ViewerMetaOut } from '@/api/types'
import { api, ApiError } from '@/api/client'
import { formatTime, taskStatusLabel } from '@/lib/format'
import { usePanelStore } from '@/stores/panel'
import EmptyState from '@/components/common/EmptyState.vue'

/**
 * 只读阅览：只订阅已存在的云端浏览器会话。
 * 打开/切换/刷新/关闭都只影响本面板的拉取，不调用任何会启动、刷新源网页或停止任务的接口。
 */
const props = defineProps<{ taskId: string | null }>()
const panel = usePanelStore()

const sessions = ref<BrowserSessionOut[]>([])
const sessionsLoaded = ref(false)
const meta = ref<ViewerMetaOut | null>(null)
const metaError = ref<string | null>(null)
const frameUrl = ref<string | null>(null)
const frameSeq = ref<number>(-1)
const noFrame = ref(false)
const lastPollOk = ref<number>(0)
const now = ref(Date.now())

let metaTimer: number | undefined
let listTimer: number | undefined
let clockTimer: number | undefined

const selectedId = computed({
  get: () => panel.browserSessionId,
  set: (v) => (panel.browserSessionId = v),
})

async function loadSessions() {
  if (!props.taskId) return
  try {
    const list = await api.taskBrowserSessions(props.taskId)
    sessions.value = list
    sessionsLoaded.value = true
    if (!selectedId.value || !list.some((s) => s.browser_session_id === selectedId.value)) {
      const pick = list.find((s) => s.session_status === 'active') ?? list[list.length - 1]
      selectedId.value = pick?.browser_session_id ?? null
    }
  } catch {
    sessionsLoaded.value = true
  }
}

function setFrame(blob: Blob | null) {
  if (frameUrl.value) URL.revokeObjectURL(frameUrl.value)
  frameUrl.value = blob ? URL.createObjectURL(blob) : null
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
    // 帧序号变化才重新取图
    if (m.frame_seq_no !== frameSeq.value && m.frame_seq_no > 0 && !m.masked) {
      const blob = await api.viewerSnapshot(id)
      if (selectedId.value !== id) return
      if (blob) {
        setFrame(blob)
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

/** 刷新阅览：只重新读取最近一帧，不刷新来源网页 */
async function refreshView() {
  frameSeq.value = -1
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
    selectedId.value = null
    frameSeq.value = -1
    setFrame(null)
    start()
  },
  { immediate: true },
)
watch(selectedId, () => {
  meta.value = null
  frameSeq.value = -1
  noFrame.value = false
  setFrame(null)
  void pollMeta()
})
onBeforeUnmount(() => {
  stop()
  setFrame(null)
})

const disconnected = computed(() => !!metaError.value || (lastPollOk.value > 0 && now.value - lastPollOk.value > 8000))
const ended = computed(() => meta.value && ['closed', 'lost', 'closing'].includes(meta.value.session_status))
const frameAge = computed(() => {
  if (!meta.value?.frame_time) return null
  const t = new Date(meta.value.frame_time.endsWith('Z') ? meta.value.frame_time : meta.value.frame_time + 'Z').getTime()
  return Math.max(0, Math.round((now.value - t) / 1000))
})
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 会话标签：切换只改变查看对象，不改变执行 Owner -->
    <div v-if="sessions.length" class="flex gap-1 overflow-x-auto border-b border-white/10 px-3 pt-2" role="tablist" aria-label="浏览器会话">
      <button
        v-for="s in sessions"
        :key="s.browser_session_id"
        role="tab"
        :aria-selected="s.browser_session_id === selectedId"
        class="flex shrink-0 items-center gap-1.5 rounded-t-lg border border-b-0 px-3 py-1.5 text-xs"
        :class="s.browser_session_id === selectedId ? 'border-white/15 bg-white/10 text-white' : 'border-transparent text-slate-400 hover:text-white'"
        @click="selectedId = s.browser_session_id"
      >
        <span class="h-1.5 w-1.5 rounded-full" :class="s.session_status === 'active' ? 'bg-emerald-400' : 'bg-slate-500'" />
        {{ s.session_label }}
      </button>
    </div>

    <div class="min-h-0 flex-1 overflow-auto p-3">
      <EmptyState
        v-if="sessionsLoaded && !sessions.length"
        title="当前任务尚未启动浏览器"
        desc="浏览器由后台根据任务需要自动启动；打开阅览不会启动采集"
      />
      <template v-else-if="selectedId">
        <div class="relative overflow-hidden rounded-xl border border-white/10 bg-black/40">
          <img v-if="frameUrl && !meta?.masked" :src="frameUrl" alt="云端浏览器最近画面截图" class="block w-full" :class="meta?.stale || ended ? 'opacity-60' : ''" />
          <div v-else-if="meta?.masked" class="flex aspect-video flex-col items-center justify-center gap-2 text-sm text-slate-400">
            <Lock class="h-6 w-6" /> 该页面因隐私策略不提供画面
          </div>
          <div v-else class="flex aspect-video items-center justify-center text-sm text-slate-500">
            {{ noFrame ? '暂无画面帧' : '正在获取画面…' }}
          </div>
          <div v-if="meta?.stale || ended" class="absolute top-2 left-2 rounded-md bg-amber-500/90 px-2 py-0.5 text-xs font-medium text-black">
            {{ ended ? '会话已结束 · 最后一帧' : '画面已过期' }}
          </div>
        </div>

        <div v-if="metaError || disconnected" class="mt-2 flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          <WifiOff class="h-4 w-4" /> {{ metaError || '阅览断连，云任务仍在后台运行' }}
        </div>

        <dl v-if="meta" class="mt-3 space-y-1.5 text-xs">
          <div class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">当前地址</dt>
            <dd class="min-w-0 flex-1 truncate font-mono text-slate-300" :title="meta.current_url || ''">{{ meta.current_url || '—' }}</dd>
          </div>
          <div v-if="meta.current_title" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">页面标题</dt>
            <dd class="min-w-0 flex-1 truncate text-slate-300">{{ meta.current_title }}</dd>
          </div>
          <div v-if="meta.current_activity" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">正在</dt>
            <dd class="text-slate-300">{{ meta.current_activity }}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-500">任务状态</dt>
            <dd class="text-slate-300">{{ taskStatusLabel(meta.task_status) }}</dd>
          </div>
        </dl>
      </template>
    </div>

    <footer class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-white/10 px-3 py-2 text-xs text-slate-400">
      <span class="flex items-center gap-1"><Info class="h-3.5 w-3.5" /> 画面定期更新 · 非实时</span>
      <span v-if="meta?.frame_time">帧时间 {{ formatTime(meta.frame_time) }}<template v-if="frameAge != null">（{{ frameAge }} 秒前）</template></span>
      <span v-if="meta && !meta.connected" class="flex items-center gap-1 text-amber-300"><AlertTriangle class="h-3.5 w-3.5" /> 浏览器未连接</span>
      <div class="flex-1" />
      <button v-if="selectedId" class="flex items-center gap-1 hover:text-white" title="只重新读取最近画面，不刷新来源网页" @click="refreshView">
        <RefreshCw class="h-3.5 w-3.5" /> 刷新阅览
      </button>
      <span class="flex items-center gap-1"><Globe class="h-3.5 w-3.5" /> 关闭阅览不停止后台任务</span>
    </footer>
  </div>
</template>
