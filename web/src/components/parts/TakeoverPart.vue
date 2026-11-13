<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { CheckCircle2, Clock, Hand, MonitorPlay, ShieldAlert, SkipForward } from 'lucide-vue-next'
import type { TakeoverPart } from '@/api/types'
import { api } from '@/api/client'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ part: TakeoverPart }>()
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
    class="flex flex-wrap items-center gap-3 rounded-2xl border border-amber-400/50 bg-amber-500/10 p-3.5"
    role="alert"
  >
    <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/20">
      <ShieldAlert class="h-5 w-5 text-amber-300" />
    </span>
    <div class="min-w-0 flex-1">
      <div class="text-sm font-semibold text-white">需要你协助：{{ part.reason }}</div>
      <div class="mt-0.5 flex items-center gap-1 text-xs text-slate-400">
        <Clock class="h-3 w-3" />
        <template v-if="part.state === 'active'">你正在处理，完成后在浏览器面板点“完成，交还给 AI”</template>
        <template v-else>AI 已暂停在该页面<template v-if="countdown">，{{ countdown }} 后将自动跳过</template></template>
      </div>
    </div>
    <template v-if="part.state === 'requested'">
      <button class="btn-primary btn-sm" :disabled="busy" @click="takeOver"><Hand class="h-3.5 w-3.5" /> 接手处理</button>
      <button class="btn-ghost btn-sm" :disabled="busy" @click="skip"><SkipForward class="h-3.5 w-3.5" /> 跳过</button>
    </template>
    <button v-else class="btn-secondary btn-sm" @click="showBrowser"><MonitorPlay class="h-3.5 w-3.5" /> 打开浏览器</button>
  </div>
  <div v-else class="flex items-center gap-2 px-1 text-xs text-slate-400">
    <CheckCircle2 class="h-3.5 w-3.5" /> 人工协助（{{ part.reason }}）：{{ finalLabel }}
  </div>
</template>
