<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { FileText, Globe, Library, Minus, X } from 'lucide-vue-next'
import { usePanelStore, type PanelType } from '@/stores/panel'
import { useChatStore } from '@/stores/chat'
import BrowserPanel from './BrowserPanel.vue'
import SourcesPanel from './SourcesPanel.vue'
import ArtifactPanel from './ArtifactPanel.vue'

const panel = usePanelStore()
const chat = useChatStore()
const narrow = ref(false)
const dragging = ref(false)
let mq: MediaQueryList | null = null

const tabs = computed(() => {
  const t: { type: PanelType; label: string; icon: typeof Globe }[] = [
    { type: 'browser', label: '云端浏览器', icon: Globe },
    { type: 'sources', label: '来源', icon: Library },
  ]
  if (panel.artifactId) t.push({ type: 'artifact', label: '成果', icon: FileText })
  return t
})

const taskOptions = computed(() => Object.values(chat.tasks).sort((a, b) => (a.created_time < b.created_time ? 1 : -1)))

function onMq() {
  narrow.value = !!mq?.matches
}
onMounted(() => {
  mq = window.matchMedia('(max-width: 1023px)')
  onMq()
  mq.addEventListener('change', onMq)
})
onBeforeUnmount(() => mq?.removeEventListener('change', onMq))

function startDrag(e: PointerEvent) {
  const container = (e.currentTarget as HTMLElement).closest('[data-split]') as HTMLElement | null
  if (!container) return
  dragging.value = true
  const rect = container.getBoundingClientRect()
  const move = (ev: PointerEvent) => {
    const px = rect.right - ev.clientX
    const minPx = 360
    const pct = (Math.max(px, minPx) / rect.width) * 100
    panel.widthPct = Math.min(60, Math.max(28, pct))
  }
  const up = () => {
    dragging.value = false
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

function onKeyResize(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') panel.widthPct = Math.min(60, panel.widthPct + 2)
  if (e.key === 'ArrowRight') panel.widthPct = Math.max(28, panel.widthPct - 2)
}
</script>

<template>
  <template v-if="panel.open">
    <div v-if="narrow" class="fixed inset-0 z-40 bg-black/40" @click="panel.close()" />
    <aside
      class="glass-strong flex min-w-[360px] flex-col overflow-hidden"
      :class="narrow ? 'fixed inset-y-0 right-0 z-50 w-full max-w-xl rounded-none' : 'relative my-3 mr-3 shrink-0'"
      :style="narrow ? undefined : { width: `${panel.widthPct}%` }"
      aria-label="右侧面板"
      @keydown.escape="panel.close()"
    >
      <div
        v-if="!narrow"
        class="absolute inset-y-0 left-0 z-10 flex w-2 cursor-col-resize items-center justify-center"
        role="separator"
        aria-orientation="vertical"
        aria-label="拖动调整面板宽度"
        tabindex="0"
        @pointerdown.prevent="startDrag"
        @keydown="onKeyResize"
      >
        <div class="h-10 w-1 rounded-full" :class="dragging ? 'bg-brand-400' : 'bg-white/20'" />
      </div>

      <header class="hairline flex items-center gap-2 border-b px-3 py-2">
        <nav class="flex gap-1" role="tablist">
          <button
            v-for="t in tabs"
            :key="t.type"
            role="tab"
            :aria-selected="panel.type === t.type"
            class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm"
            :class="panel.type === t.type ? 'bg-white/5 font-medium text-white' : 'text-slate-400 hover:text-white'"
            @click="panel.setType(t.type)"
          >
            <component :is="t.icon" class="h-4 w-4" /> {{ t.label }}
          </button>
        </nav>
        <span
          v-if="panel.type === 'browser' && panel.interactiveSessionId"
          class="rounded-full bg-brand-500 px-2 py-0.5 text-xs text-snow"
        >人工操作</span>
        <span v-else-if="panel.type === 'browser'" class="rounded-full border border-brand-400/40 bg-brand-500/10 px-2 py-0.5 text-xs text-brand-300">只读阅览</span>
        <div class="flex-1" />
        <label v-if="panel.type !== 'artifact' && taskOptions.length > 1" class="sr-only" for="cs-panel-task">选择任务</label>
        <select
          v-if="panel.type !== 'artifact' && taskOptions.length > 1"
          id="cs-panel-task"
          v-model="panel.taskId"
          class="input max-w-[160px] truncate !py-1 !text-xs"
        >
          <option v-for="t in taskOptions" :key="t.task_id" :value="t.task_id">{{ t.title }}</option>
        </select>
        <button class="icon-btn" aria-label="最小化面板" title="最小化（不影响后台任务）" @click="panel.close()"><Minus class="h-4 w-4" /></button>
        <button class="icon-btn" aria-label="关闭面板" title="关闭阅览不停止后台任务" @click="panel.close()"><X class="h-4 w-4" /></button>
      </header>

      <div class="min-h-0 flex-1">
        <BrowserPanel v-if="panel.type === 'browser'" :task-id="panel.taskId" />
        <SourcesPanel v-else-if="panel.type === 'sources'" :task-id="panel.taskId" :focus-n="panel.focusN" />
        <ArtifactPanel v-else :artifact-id="panel.artifactId" />
      </div>
    </aside>
  </template>
</template>
