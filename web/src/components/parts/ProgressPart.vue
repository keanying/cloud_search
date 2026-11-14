<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Globe, Library, Loader2, MoreHorizontal, Search } from 'lucide-vue-next'
import type { ProgressPart, TaskOut } from '@/api/types'
import { api } from '@/api/client'
import { ACTIVE_STATUSES, TERMINAL_STATUSES, formatDuration, taskStatusEmoji, taskStatusLabel, taskStatusTone } from '@/lib/format'
import { useNow } from '@/lib/useNow'
import { useChatStore } from '@/stores/chat'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'
import StatusBadge from '@/components/common/StatusBadge.vue'
import StageTimeline from '@/components/task/StageTimeline.vue'
import StatTiles from '@/components/task/StatTiles.vue'
import { useFloating } from '@/lib/useFloating'

const props = defineProps<{ part: ProgressPart }>()
const chat = useChatStore()
const panel = usePanelStore()
const toast = useToastStore()
const menuOpen = ref(false)
const busy = ref(false)
const menuRoot = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const { style: menuStyle } = useFloating(menuRoot, menuEl, menuOpen, () => 'top-start')

const task = computed<TaskOut | undefined>(() => chat.tasks[props.part.task_id])
const status = computed(() => task.value?.task_status ?? props.part.task_status)
const active = computed(() => ACTIVE_STATUSES.has(status.value))
const counters = computed(() => {
  const c = props.part.counters || {}
  const out: { label: string; value: number; tone?: 'white' }[] = []
  if (c.queries != null) out.push({ label: '搜索', value: c.queries })
  if (c.candidates != null) out.push({ label: '候选', value: c.candidates })
  if (c.sources_read != null) out.push({ label: '已读来源', value: c.sources_read })
  if (c.sources_failed) out.push({ label: '读取受限/失败', value: c.sources_failed })
  if (c.evidence != null) out.push({ label: '证据', value: c.evidence })
  return out
})

// 耗时：进行中时每秒刷新（总用时按开始时间计算；进行中阶段在最近一次数据基础上累加）
const running = computed(() => !TERMINAL_STATUSES.has(status.value) && status.value !== 'draft')
const now = useNow(running)
const receivedAt = ref(Date.now())
watch(() => props.part, () => (receivedAt.value = Date.now()), { deep: true })
const liveExtra = computed(() => (running.value ? Math.max(0, now.value - receivedAt.value) : 0))
const elapsed = computed(() => {
  const m = props.part.metrics
  if (!m?.started_ms) return null
  return running.value ? Math.max(m.elapsed_ms ?? 0, now.value - m.started_ms) : m.elapsed_ms
})
const metricsLine = computed(() => {
  const m = props.part.metrics
  if (!m) return ''
  const bits: string[] = []
  if (elapsed.value != null) bits.push(`${running.value ? '已用时' : '总用时'} ${formatDuration(elapsed.value)}`)
  if (m.llm_requests) bits.push(`模型调用 ${m.llm_requests} 次`)
  if (m.spent_minor_amt) bits.push(`费用 ¥${(m.spent_minor_amt / 100).toFixed(2)}`)
  if (m.cost_unknown_qty) bits.push(`${m.cost_unknown_qty} 次待核算`)
  return bits.join(' · ')
})

const canPause = computed(() => status.value === 'queued' || status.value === 'running')
const canResume = computed(() => status.value === 'paused')
const canContinue = computed(() => TERMINAL_STATUSES.has(status.value))

async function downloadTrace() {
  menuOpen.value = false
  try {
    await api.downloadTaskTrace(props.part.task_id)
  } catch (e) {
    toast.error(e, '下载执行日志失败')
  }
}

async function run(fn: () => Promise<TaskOut>, okText: string) {
  menuOpen.value = false
  busy.value = true
  try {
    const t = await fn()
    chat.upsertTask(t)
    toast.push(okText, 'info')
  } catch (e) {
    toast.error(e)
    void chat.refreshTask(props.part.task_id)
  } finally {
    busy.value = false
  }
}

</script>

<template>
  <div class="card-mint p-5">
    <div class="flex flex-wrap items-center gap-2">
      <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--cs-surface-solid)]">
        <Loader2 v-if="active" class="h-4 w-4 animate-spin accent-ink" />
        <Check v-else-if="status === 'completed'" class="h-4 w-4 accent-ink" stroke-width="3" />
        <Search v-else class="h-4 w-4 accent-ink" />
      </span>
      <div class="min-w-0 flex-1">
        <div class="truncate text-[15px] font-bold tracking-tight text-white">{{ task?.title || part.stage_label || '任务进度' }}</div>
        <div v-if="part.stage_label && active" class="truncate text-xs accent-ink">{{ part.stage_label }}</div>
        <div v-if="metricsLine" class="truncate text-xs text-slate-400 tabular-nums">{{ metricsLine }}</div>
      </div>
      <StatusBadge :tone="taskStatusTone(status)" :emoji="taskStatusEmoji(status, task?.status_reason)">
        {{ taskStatusLabel(status, task?.status_reason) }}
      </StatusBadge>
    </div>

    <div class="mt-4 grid gap-4" :class="part.stages?.length && counters.length ? 'sm:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]' : ''">
      <StageTimeline v-if="part.stages?.length" :stages="part.stages" dense :live-extra-ms="liveExtra" />
      <StatTiles v-if="counters.length" :items="counters" class="content-start !grid-cols-2" />
    </div>

    <p v-if="task?.error_desc && (status === 'failed' || status === 'partial_failed')" class="mt-3 text-xs text-rose-300">
      {{ task.error_desc }}
    </p>
    <p v-if="status === 'stopped'" class="mt-3 text-xs text-slate-300">已停止。停止前已提交的来源与成果已保留。</p>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <button v-if="part.browser_available" class="btn-primary btn-sm" @click="panel.openBrowserModal(part.task_id)">
        <Globe class="h-3.5 w-3.5" /> 查看浏览器
      </button>
      <button class="btn-secondary btn-sm" @click="panel.openSources(part.task_id)">
        <Library class="h-3.5 w-3.5" /> 来源
      </button>
      <div v-if="canPause || canResume || canContinue" ref="menuRoot" class="relative">
        <button class="round-btn-light !h-8 !w-8" :disabled="busy" aria-label="更多操作" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
          <Loader2 v-if="busy" class="h-4 w-4 animate-spin" />
          <MoreHorizontal v-else class="h-4 w-4" />
        </button>
        <Teleport to="body">
        <div v-if="menuOpen" ref="menuEl" role="menu" class="popover-menu w-44" :style="menuStyle">
          <button
            v-if="canPause"
            role="menuitem"
            class="block w-full rounded-xl px-3 py-2 text-left text-sm hover:bg-white/10"
            @click="run(() => api.pauseTask(part.task_id), '已请求暂停，将在安全点暂停')"
          >
            暂停
          </button>
          <button
            v-if="canResume"
            role="menuitem"
            class="block w-full rounded-xl px-3 py-2 text-left text-sm hover:bg-white/10"
            @click="run(() => api.resumeTask(part.task_id), '已请求继续')"
          >
            继续
          </button>
          <button
            v-if="canContinue"
            role="menuitem"
            class="block w-full rounded-xl px-3 py-2 text-left text-sm hover:bg-white/10"
            title="创建新任务处理剩余缺口，旧成果保持不变"
            @click="run(() => api.continueTask(part.task_id), '已创建续做任务，旧成果不会被修改')"
          >
            继续补查（新任务）
          </button>
          <button
            role="menuitem"
            class="block w-full rounded-xl px-3 py-2 text-left text-sm hover:bg-white/10"
            title="包含每一步的耗时、搜索与读取结果、验证判定原因和模型调用，出现问题时可以发给开发者排查"
            @click="downloadTrace"
          >
            下载执行日志
          </button>
        </div>
        </Teleport>
      </div>
    </div>
  </div>
</template>
