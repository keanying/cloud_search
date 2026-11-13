<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { FileText, Globe, Library, X } from 'lucide-vue-next'
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
    const minPx = 380
    const pct = (Math.max(px, minPx) / rect.width) * 100
    panel.widthPct = Math.min(55, Math.max(28, pct))
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
  if (e.key === 'ArrowLeft') panel.widthPct = Math.min(55, panel.widthPct + 2)
  if (e.key === 'ArrowRight') panel.widthPct = Math.max(28, panel.widthPct - 2)
}
</script>

<template>
  <template v-if="panel.open">
    <div v-if="narrow" class="fixed inset-0 z-40 bg-black/40" @click="panel.close()" />
    <aside
      class="glass-strong flex flex-col overflow-hidden"
      :class="narrow ? 'fixed inset-0 z-50 w-full !rounded-none sm:inset-y-0 sm:left-auto sm:max-w-xl sm:!rounded-l-[28px]' : 'relative min-w-[380px] shrink-0 !rounded-[28px]'"
      :style="narrow ? undefined : { width: `${Math.min(panel.widthPct, 55)}%` }"
      aria-label="右侧面板"
      @keydown.escape="panel.close()"
    >
      <div
        v-if="!narrow"
        class="absolute inset-y-0 left-0 z-10 flex w-3 cursor-col-resize items-center justify-center"
        role="separator"
        aria-orientation="vertical"
        aria-label="拖动调整面板宽度"
        tabindex="0"
        @pointerdown.prevent="startDrag"
        @keydown="onKeyResize"
      >
        <div class="h-12 w-1 rounded-full" :class="dragging ? 'bg-[var(--cs-ink)]' : 'bg-white/20'" />
      </div>

      <header class="hairline flex items-center gap-2 border-b py-2.5 pr-2.5 pl-4">
        <nav class="sunken flex gap-0.5 rounded-full p-1" role="tablist">
          <button
            v-for="t in tabs"
            :key="t.type"
            role="tab"
            :aria-selected="panel.type === t.type"
            class="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold"
            :class="panel.type === t.type ? 'chip-active' : 'text-slate-400 hover:text-white'"
            @click="panel.setType(t.type)"
          >
            <component :is="t.icon" class="h-4 w-4" /> {{ t.label }}
          </button>
        </nav>
        <span
          v-if="panel.type === 'browser' && panel.interactiveSessionId"
          class="pill card-butter accent-ink"
        >✋ 人工操作</span>
        <span v-else-if="panel.type === 'browser'" class="pill card-mint accent-ink">👀 只读阅览</span>
        <div class="flex-1" />
        <label v-if="panel.type !== 'artifact' && taskOptions.length > 1" class="sr-only" for="cs-panel-task">选择任务</label>
        <select
          v-if="panel.type !== 'artifact' && taskOptions.length > 1"
          id="cs-panel-task"
          v-model="panel.taskId"
          class="input max-w-[160px] truncate !rounded-full !py-1.5 !text-xs"
        >
          <option v-for="t in taskOptions" :key="t.task_id" :value="t.task_id">{{ t.title }}</option>
        </select>
        <button class="round-btn-light !h-9 !w-9" aria-label="关闭面板，回到任务看板" title="关闭阅览不停止后台任务" @click="panel.close()"><X class="h-4 w-4" /></button>
      </header>

      <div class="min-h-0 flex-1">
        <BrowserPanel v-if="panel.type === 'browser'" :task-id="panel.taskId" />
        <SourcesPanel v-else-if="panel.type === 'sources'" :task-id="panel.taskId" :focus-n="panel.focusN" />
        <ArtifactPanel v-else :artifact-id="panel.artifactId" />
      </div>
    </aside>
  </template>
</template>
