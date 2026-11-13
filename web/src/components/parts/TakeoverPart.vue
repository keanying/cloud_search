<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { CheckCircle2, Clock, Hand, MonitorPlay, ShieldAlert, SkipForward } from 'lucide-vue-next'
import type { TakeoverPart } from '@/api/types'
import { api } from '@/api/client'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ part: TakeoverPart; compact?: boolean }>()
const panel = usePanelStore()
const toast = useToastStore()
const busy = ref(false)
const now = ref(Date.now())
let timer: number | undefined
onMounted(() => (timer = window.setInterval(() => (now.value = Date.now()), 1000)))
onBeforeUnmount(() => window.clearInterval(timer))

const open = computed(() => props.part.state === 'requested' || props.part.state === 'active')
const countdown = computed(() => {
  const d = props.part.deadline_time
  if (!d || !open.value) return null
  const t = new Date(d.endsWith('Z') || d.includes('+') ? d : d + 'Z').getTime()
  const s = Math.max(0, Math.round((t - now.value) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})
const finalLabel = computed(
  () => ({ resolved: '已处理，任务继续', timeout: '等待超时，AI 已改用其他来源', skipped: '已跳过，AI 已改用其他来源' })[
    props.part.state as 'resolved' | 'timeout' | 'skipped'
  ] ?? '',
)

function showBrowser() {
  panel.openBrowser(props.part.task_id, props.part.browser_session_id)
}

async function takeOver() {
  busy.value = true
  try {
    await api.takeover(props.part.browser_session_id)
    panel.interactiveSessionId = props.part.browser_session_id
    showBrowser()
  } catch (e) {
    toast.error(e, '接手失败')
  } finally {
    busy.value = false
  }
}

async function skip() {
  busy.value = true
  try {
    await api.takeoverReturn(props.part.browser_session_id, false)
  } catch (e) {
    toast.error(e, '操作失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    v-if="open"
    class="card-butter takeover-tilt relative p-5"
    :class="compact ? '' : 'max-w-xl'"
    role="alert"
  >
    <div class="flex items-center gap-2">
      <span class="cs-ping h-2.5 w-2.5 rounded-full accent-dot text-[var(--accent-dot)]" aria-hidden="true" />
      <span class="pill bg-[var(--cs-surface-solid)] text-slate-100">✋ 需要你</span>
      <div class="flex-1" />
      <span v-if="countdown" class="pill bg-[var(--cs-surface-solid)] font-mono text-slate-200 tabular-nums">
        <Clock class="h-3 w-3" /> {{ countdown }}
      </span>
    </div>
    <div class="mt-3 flex items-start gap-3">
      <span v-if="!compact" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--cs-surface-solid)]">
        <ShieldAlert class="h-5 w-5 accent-ink" />
      </span>
      <div class="min-w-0 flex-1">
        <div class="text-[15px] leading-6 font-bold tracking-tight text-white">{{ part.reason }}</div>
        <div class="mt-1 text-xs accent-ink">
          <template v-if="part.state === 'active'">你正在处理，完成后在浏览器面板点“完成，交还给 AI”</template>
          <template v-else>AI 已暂停在该页面<template v-if="countdown">，到时将自动跳过</template></template>
        </div>
      </div>
    </div>
    <div class="mt-4 flex flex-wrap gap-2">
      <template v-if="part.state === 'requested'">
        <button class="btn-primary btn-sm" :disabled="busy" @click="takeOver"><Hand class="h-3.5 w-3.5" /> 接手处理</button>
        <button class="btn-secondary btn-sm" :disabled="busy" @click="skip"><SkipForward class="h-3.5 w-3.5" /> 跳过</button>
      </template>
      <button v-else class="btn-primary btn-sm" @click="showBrowser"><MonitorPlay class="h-3.5 w-3.5" /> 打开浏览器</button>
    </div>
  </div>
  <div v-else-if="!compact" class="flex items-center gap-2 px-1 text-xs text-slate-400">
    <CheckCircle2 class="h-3.5 w-3.5" /> 人工协助（{{ part.reason }}）：{{ finalLabel }}
  </div>
</template>

<style scoped>
.takeover-tilt {
  transform: rotate(-1.5deg);
  box-shadow: 0 14px 30px -18px rgba(90, 72, 8, 0.45);
}
@media (prefers-reduced-motion: reduce) {
  .takeover-tilt {
    transform: none;
  }
}
</style>
