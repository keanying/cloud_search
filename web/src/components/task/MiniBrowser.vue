<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Globe, Maximize2, Minus, MonitorPlay } from 'lucide-vue-next'
import type { BrowserSessionOut } from '@/api/types'
import { api } from '@/api/client'
import { useLiveView } from '@/lib/useLiveView'
import { usePanelStore } from '@/stores/panel'

/** 搜索/读取网页时的浏览器小窗：只显示云端浏览器画面；点击放大到右侧完整面板。 */
const props = defineProps<{ taskId: string; active: boolean }>()
const panel = usePanelStore()
const sessions = ref<BrowserSessionOut[]>([])
const collapsed = ref(false)
const snapUrl = ref<string | null>(null)
let seq = -1
let timer: number | undefined

const session = computed(
  () =>
    sessions.value.find((s) => s.handoff_state === 'requested' || s.handoff_state === 'active') ??
    sessions.value.find((s) => s.session_status === 'active') ??
    null,
)
const sessionId = computed(() => session.value?.browser_session_id ?? null)
// 居中大窗打开时小窗暂停实时连接：画面与操作都只走大窗这一条连接
const liveOn = computed(() => props.active && !collapsed.value && !!sessionId.value && !panel.modalTaskId)
const live = useLiveView(sessionId, liveOn)
const src = computed(() => (live.connected.value && live.frameSrc.value) || snapUrl.value)
// 浏览器还停在空白页（搜索与读取正走 HTTP）：显示待命说明而不是白屏
const blank = computed(() => {
  const u = (live.connected.value && live.frameUrl.value) || session.value?.current_url || ''
  return !u || u.startsWith('about:') || u.startsWith('chrome://new')
})
const needsHuman = computed(() => !!session.value && ['requested', 'active'].includes(session.value.handoff_state ?? ''))

async function poll() {
  if (!props.active || document.hidden) return
  try {
    sessions.value = await api.taskBrowserSessions(props.taskId)
    const id = sessionId.value
    if (!id || collapsed.value || (live.connected.value && live.frameSrc.value)) return
    const m = await api.viewerMeta(id) // 实时通道不可用时退回截图
    if (m.frame_seq_no > 0 && m.frame_seq_no !== seq && !m.masked) {
      const blob = await api.viewerSnapshot(id)
      if (blob) {
        if (snapUrl.value) URL.revokeObjectURL(snapUrl.value)
        snapUrl.value = URL.createObjectURL(blob)
        seq = m.frame_seq_no
      }
    }
  } catch {
    /* 小窗是辅助信息，失败时静默 */
  }
}
watch(
  () => [props.taskId, props.active] as const,
  () => {
    window.clearInterval(timer)
    if (props.active) {
      void poll()
      timer = window.setInterval(poll, 2500)
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  window.clearInterval(timer)
  if (snapUrl.value) URL.revokeObjectURL(snapUrl.value)
})

function maximize() {
  panel.openBrowserModal(props.taskId, sessionId.value) // 居中大窗，只显示浏览器
}
</script>

<template>
  <div v-if="active && sessionId" class="mini-browser">
    <button v-if="collapsed" class="mini-pill" aria-label="展开浏览器小窗" @click="collapsed = false">
      <MonitorPlay class="h-4 w-4" />
    </button>
    <div v-else class="mini-frame group" :class="needsHuman ? 'ring-2 ring-amber-400' : ''">
      <button class="block h-full w-full" aria-label="放大查看云端浏览器" @click="maximize">
        <span v-if="blank && !needsHuman" class="idle flex h-full w-full flex-col items-center justify-center gap-1.5 px-3 text-center">
          <Globe class="h-5 w-5 text-brand-400" />
          <span class="text-xs font-semibold text-slate-100">浏览器待命中</span>
          <span class="line-clamp-2 text-[11px] leading-4 text-slate-400">{{ session?.current_activity || '正在用 HTTP 直接读取，必要时才打开浏览器' }}</span>
        </span>
        <img v-else-if="src" :src="src" alt="云端浏览器实时画面" class="h-full w-full object-cover object-top" draggable="false" />
        <span v-else class="flex h-full w-full items-center justify-center">
          <span class="h-2 w-2 animate-pulse rounded-full bg-slate-400" />
        </span>
      </button>
      <div class="absolute top-1.5 right-1.5 flex gap-1 opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100">
        <button class="mini-btn" aria-label="收起小窗" @click.stop="collapsed = true"><Minus class="h-3.5 w-3.5" /></button>
        <button class="mini-btn" aria-label="放大" @click.stop="maximize"><Maximize2 class="h-3.5 w-3.5" /></button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mini-browser {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
  z-index: 5;
}
.mini-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid var(--cs-rim);
  background: var(--color-ink-900);
  box-shadow: var(--cs-shadow-lg);
}
.mini-pill {
  display: inline-flex;
  height: 36px;
  width: 36px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--cs-ink);
  color: var(--cs-on-ink);
  box-shadow: var(--cs-shadow-lg);
}
.mini-btn {
  display: inline-flex;
  height: 26px;
  width: 26px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgb(17 18 20 / 0.72);
  color: #fff;
}
</style>
