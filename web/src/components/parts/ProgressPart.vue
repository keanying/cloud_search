<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, Circle, Globe, Library, Loader2, MinusCircle, MoreHorizontal, XCircle } from 'lucide-vue-next'
import type { ProgressPart, TaskOut } from '@/api/types'
import { api } from '@/api/client'
import { ACTIVE_STATUSES, TERMINAL_STATUSES, taskStatusLabel, taskStatusTone } from '@/lib/format'
import { useChatStore } from '@/stores/chat'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'
import StatusBadge from '@/components/common/StatusBadge.vue'
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
  const out: { label: string; value: number }[] = []
  if (c.queries != null) out.push({ label: '搜索', value: c.queries })
  if (c.candidates != null) out.push({ label: '候选', value: c.candidates })
  if (c.sources_read != null) out.push({ label: '已读来源', value: c.sources_read })
  if (c.sources_failed) out.push({ label: '读取受限/失败', value: c.sources_failed })
  if (c.evidence != null) out.push({ label: '证据', value: c.evidence })
  return out
})

const canPause = computed(() => status.value === 'queued' || status.value === 'running')
const canResume = computed(() => status.value === 'paused')
const canContinue = computed(() => TERMINAL_STATUSES.has(status.value))

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
  <div class="glass p-4">
    <div class="flex flex-wrap items-center gap-2">
      <Loader2 v-if="active" class="h-4 w-4 animate-spin text-brand-300" />
      <span class="text-sm font-semibold text-white">{{ part.stage_label || task?.title || '任务进度' }}</span>
      <div class="flex-1" />
      <StatusBadge :tone="taskStatusTone(status)" :pulse="active">{{ taskStatusLabel(status, task?.status_reason) }}</StatusBadge>
    </div>

    <ul v-if="part.stages?.length" class="mt-3 space-y-1.5">
      <li v-for="s in part.stages" :key="s.key" class="flex items-center gap-2 text-sm">
        <Check v-if="s.status === 'done'" class="h-4 w-4 text-emerald-300" />
        <Loader2 v-else-if="s.status === 'running'" class="h-4 w-4 animate-spin text-brand-300" />
        <XCircle v-else-if="s.status === 'failed'" class="h-4 w-4 text-rose-300" />
        <MinusCircle v-else-if="s.status === 'skipped'" class="h-4 w-4 text-slate-500" />
        <Circle v-else class="h-4 w-4 text-slate-600" />
        <span :class="s.status === 'pending' || s.status === 'skipped' ? 'text-slate-500' : 'text-slate-200'">{{ s.label }}</span>
        <span v-if="s.status === 'skipped'" class="text-xs text-slate-600">（跳过）</span>
      </li>
    </ul>

    <div v-if="counters.length" class="mt-3 flex flex-wrap gap-2">
      <span v-for="c in counters" :key="c.label" class="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-300">
        {{ c.label }} <b class="text-white">{{ c.value }}</b>
      </span>
    </div>

    <p v-if="task?.error_desc && (status === 'failed' || status === 'partial_failed')" class="mt-3 text-xs text-rose-300">
      {{ task.error_desc }}
    </p>
    <p v-if="status === 'stopped'" class="mt-3 text-xs text-slate-400">已停止。停止前已提交的来源与成果已保留。</p>

    <div class="mt-3 flex flex-wrap items-center gap-2">
      <button v-if="part.browser_available" class="btn-secondary btn-sm" @click="panel.openBrowser(part.task_id)">
        <Globe class="h-3.5 w-3.5" /> 查看浏览器
      </button>
      <button class="btn-secondary btn-sm" @click="panel.openSources(part.task_id)">
        <Library class="h-3.5 w-3.5" /> 来源
      </button>
      <div v-if="canPause || canResume || canContinue" ref="menuRoot" class="relative">
        <button class="icon-btn" :disabled="busy" aria-label="更多操作" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
          <Loader2 v-if="busy" class="h-4 w-4 animate-spin" />
          <MoreHorizontal v-else class="h-4 w-4" />
        </button>
        <Teleport to="body">
        <div v-if="menuOpen" ref="menuEl" role="menu" class="popover-menu w-44" :style="menuStyle">
          <button
            v-if="canPause"
            role="menuitem"
            class="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-white/10"
            @click="run(() => api.pauseTask(part.task_id), '已请求暂停，将在安全点暂停')"
          >
            暂停
          </button>
          <button
            v-if="canResume"
            role="menuitem"
            class="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-white/10"
            @click="run(() => api.resumeTask(part.task_id), '已请求继续')"
          >
            继续
          </button>
          <button
            v-if="canContinue"
            role="menuitem"
            class="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-white/10"
            title="创建新任务处理剩余缺口，旧成果保持不变"
            @click="run(() => api.continueTask(part.task_id), '已创建续做任务，旧成果不会被修改')"
          >
            继续补查（新任务）
          </button>
        </div>
        </Teleport>
      </div>
    </div>
  </div>
</template>
