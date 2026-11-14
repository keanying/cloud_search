<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { FileUp, LayoutDashboard, Loader2, PanelLeftOpen, WifiOff } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import MessageList from '@/components/chat/MessageList.vue'
import RightPanel from '@/components/panel/RightPanel.vue'
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import TaskDashboard from '@/components/task/TaskDashboard.vue'
import BrowserModal from '@/components/panel/BrowserModal.vue'
import { WIDE_QUERY, useMedia } from '@/lib/useMedia'
import { useUiStore } from '@/stores/ui'
import { ChatActionsKey } from '@/lib/chatActions'
import { taskStatusLabel } from '@/lib/format'
import { useChatStore } from '@/stores/chat'
import { usePrefsStore } from '@/stores/prefs'
import type { ProgressPart, TakeoverPart } from '@/api/types'
import { ACTIVE_STATUSES } from '@/lib/format'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'
import { useAttachments } from '@/lib/useAttachments'

const props = defineProps<{ id: string }>()
const chat = useChatStore()
const panel = usePanelStore()
const toast = useToastStore()
const prefs = usePrefsStore()
const ui = useUiStore()
const wide = useMedia(WIDE_QUERY)

/** “本次任务”：宽屏关闭右侧面板回到看板；窄屏打开看板抽屉 */
function showDashboard() {
  if (wide.value) panel.close()
  else {
    panel.close()
    ui.dashboardDrawer = true
  }
}

const text = ref('')
const mode = ref<ModeSelection>('auto')
const hint = ref<string | null>(null)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
const list = ref<InstanceType<typeof MessageList> | null>(null)
const stopSubmitting = ref(false)

// ---------------------------------------------------------------- 附件：选择 / 拖放 / 粘贴后立即上传
const attachments = useAttachments(async () => props.id)
watch(
  () => chat.files,
  (files) => {
    for (const a of attachments.items.value) {
      const f = a.file && files[a.file.file_id]
      if (f) attachments.apply(f)
    }
  },
  { deep: true },
)
const dragDepth = ref(0)
const dragging = computed(() => dragDepth.value > 0)
function hasFiles(e: DragEvent) {
  return Array.from(e.dataTransfer?.types ?? []).includes('Files')
}
function onDragEnter(e: DragEvent) {
  if (!hasFiles(e)) return
  e.preventDefault()
  dragDepth.value++
}
function onDragOver(e: DragEvent) {
  if (!hasFiles(e)) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
}
function onDragLeave(e: DragEvent) {
  if (!hasFiles(e)) return
  dragDepth.value = Math.max(0, dragDepth.value - 1)
}
// 拖到对话区以外时阻止浏览器直接打开文件
function blockWindowDrop(e: DragEvent) {
  if (hasFiles(e)) e.preventDefault()
}
onMounted(() => {
  window.addEventListener('dragover', blockWindowDrop)
  window.addEventListener('drop', blockWindowDrop)
})
onBeforeUnmount(() => {
  window.removeEventListener('dragover', blockWindowDrop)
  window.removeEventListener('drop', blockWindowDrop)
})
function onDrop(e: DragEvent) {
  if (!hasFiles(e)) return
  e.preventDefault()
  dragDepth.value = 0
  attachments.add(e.dataTransfer?.files)
  composer.value?.focus()
}

provide(ChatActionsKey, {
  focusComposer(h?: string) {
    hint.value = h ?? null
    composer.value?.focus()
  },
  ask(t: string) {
    if (stopSubmitting.value) return
    text.value = t
    void submit()
  },
})

watch(
  () => props.id,
  async (id) => {
    panel.reset()
    ui.sidebarDrawer = false
    ui.dashboardDrawer = false
    ui.setLastChat(id)
    text.value = ''
    hint.value = null
    attachments.clear()
    await chat.open(id)
    list.value?.scrollToBottom(false)
  },
  { immediate: true },
)

// 离开页面只关闭事件订阅，不停止任何云端任务
onBeforeUnmount(() => chat.close())

async function submit() {
  const t = text.value.trim()
  const fileIds = attachments.fileIds.value
  if ((!t && !fileIds.length) || attachments.uploading.value) return
  try {
    await chat.send(t, mode.value, fileIds)
    attachments.clear()
    text.value = ''
    hint.value = null
    list.value?.scrollToBottom()
  } catch (e) {
    toast.error(e, '发送失败，输入内容已保留')
  }
}

const activeLabel = computed(() =>
  chat.activeTasks.map((t) => `${t.title}（${taskStatusLabel(t.task_status)}）`).join('、'),
)

async function stopTurn() {
  if (stopSubmitting.value) return
  stopSubmitting.value = true
  try {
    const res = await chat.stopTurn()
    const accepted = res?.results.filter((r) => r.outcome === 'accepted').length ?? 0
    if (accepted) toast.push(`已发送停止命令（${accepted} 个任务），等待后台确认`, 'info')
    else toast.push('当前轮没有需要停止的任务', 'info')
  } catch (e) {
    toast.error(e, '停止命令发送失败')
  } finally {
    stopSubmitting.value = false
  }
}

/**
 * 自动打开浏览器阅览：
 * - 任务开始使用云端浏览器（progress.browser_available）且仍在执行时，按设置自动打开一次；用户关闭后同一任务不再弹出
 * - 任务请求人工协助（takeover 卡片 requested）时，总是打开到对应会话
 */
const handledTakeovers = new Set<string>()
watch(
  () => chat.messages.flatMap((m) => m.parts.filter((p) => p.type === 'progress' || p.type === 'takeover')),
  (parts) => {
    for (const p of parts) {
      if (p.type === 'takeover') {
        const t = p as TakeoverPart
        if (t.state === 'requested' && !handledTakeovers.has(t.part_id)) {
          handledTakeovers.add(t.part_id)
          // 需要你处理验证：宽屏在居中大窗里打开（只显示浏览器和操作条），窄屏用右侧面板
          if (wide.value) panel.openBrowserModal(t.task_id, t.browser_session_id)
          else panel.openBrowser(t.task_id, t.browser_session_id)
        }
        continue
      }
      const pr = p as ProgressPart
      const status = chat.tasks[pr.task_id]?.task_status ?? pr.task_status
      if (!prefs.autoOpenBrowser || !pr.browser_available || !ACTIVE_STATUSES.has(status)) continue
      if (wide.value) continue // 宽屏：右侧“本次任务”底部有浏览器小窗，点击再放大，不自动占满右栏
      if (panel.autoOpenedTaskIds.includes(pr.task_id)) continue
      panel.autoOpenBrowser(pr.task_id)
    }
  },
  { deep: true },
)

// 只有后端确认停止后才提示
watch(
  () => chat.isStopping,
  (now, before) => {
    if (before && !now && chat.stoppingTaskIds.length) {
      toast.push('后台已确认停止，停止前已提交的成果已保留', 'success')
      chat.stoppingTaskIds = []
    }
  },
)
</script>

<template>
  <div class="flex h-full gap-3 p-3 xl:gap-4" data-split>
    <!-- 左：对话列表（宽屏常驻，可收起） -->
    <ConversationSidebar
      v-if="wide && !ui.sidebarCollapsed"
      class="w-[244px] shrink-0 min-[1440px]:w-[272px]"
      :current-id="id"
      @collapse="ui.setSidebarCollapsed(true)"
    />

    <!-- 中：对话 -->
    <section
      class="relative flex min-w-0 flex-1 flex-col"
      @dragenter="onDragEnter"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div v-if="dragging" class="drop-overlay" aria-hidden="true">
        <div class="drop-box">
          <FileUp class="h-8 w-8" />
          <div class="text-lg font-bold">松开即可上传</div>
          <div class="text-sm opacity-80">PDF、Word、Excel、PPT、图片、TXT / Markdown… 单个不超过 100MB</div>
        </div>
      </div>
      <div class="mx-auto flex w-full max-w-[860px] items-center gap-2 px-4 pt-1 pb-2 md:px-6">
        <button
          v-if="wide && ui.sidebarCollapsed"
          class="round-btn-light !h-9 !w-9"
          aria-label="展开对话列表"
          title="展开对话列表"
          @click="ui.setSidebarCollapsed(false)"
        >
          <PanelLeftOpen class="h-4 w-4" />
        </button>
        <div class="min-w-0 flex-1">
          <h1 class="truncate text-[19px] leading-7 font-bold tracking-tight text-white">{{ chat.conversation?.title || '对话' }}</h1>
        </div>
        <button v-if="!wide || panel.open" class="btn-secondary btn-sm !py-2" @click="showDashboard">
          <LayoutDashboard class="h-4 w-4" /> 本次任务
          <span v-if="chat.hasActive" class="cs-ping h-2 w-2 rounded-full bg-brand-500 text-brand-500" aria-label="有任务执行中" />
        </button>
      </div>
      <div
        v-if="chat.streamStatus === 'reconnecting'"
        class="mx-auto mb-1 flex items-center gap-2 rounded-full card-butter px-3 py-1 text-xs font-medium accent-ink"
        role="status"
      >
        <WifiOff class="h-3.5 w-3.5" /> 连接中断，正在重连…后台任务不受影响
      </div>

      <div v-if="chat.loading && !chat.messages.length" class="flex flex-1 items-center justify-center text-sm text-slate-400">
        <Loader2 class="mr-2 h-4 w-4 animate-spin" /> 正在加载对话…
      </div>
      <div v-else-if="chat.loadError" class="flex flex-1 flex-col items-center justify-center gap-3 text-sm">
        <span class="text-rose-300">{{ chat.loadError }}</span>
        <button class="btn-secondary" @click="chat.open(props.id)">重试</button>
      </div>
      <MessageList v-else ref="list" :messages="chat.messages" />

      <div class="mx-auto w-full max-w-[860px] px-2 md:px-6">
        <div v-if="chat.hasActive" class="mb-1.5 flex items-center gap-1.5 truncate px-2 text-xs text-slate-500" :title="activeLabel">
          <span class="cs-ping h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500 text-brand-500" aria-hidden="true" />
          后台任务：{{ activeLabel }}
        </div>
        <ChatComposer
          ref="composer"
          v-model="text"
          v-model:mode="mode"
          variant="chat"
          :hint="hint"
          :sending="chat.sending"
          :disabled="!!chat.loadError"
          placeholder="继续补充要求…"
          :show-stop="chat.hasActive"
          :attachments="attachments.items.value"
          :uploading="attachments.uploading.value"
          :stopping="chat.isStopping || stopSubmitting"
          stop-hint="停止最近一轮关联的任务；已提交成果会保留"
          @submit="submit"
          @stop="stopTurn"
          @pick="attachments.add"
          @remove-file="attachments.remove"
          @retry-file="attachments.retry"
          @open-file="panel.openFile"
        />
      </div>
    </section>

    <!-- 右：浏览器/来源/成果面板，或“本次任务”看板 -->
    <RightPanel />
    <TaskDashboard v-if="wide && !panel.open" class="w-[340px] shrink-0 min-[1440px]:w-[380px]" />

    <!-- 窄屏抽屉 -->
    <Teleport to="body">
      <div v-if="!wide && ui.sidebarDrawer" class="fixed inset-0 z-50 flex" @keydown.escape="ui.sidebarDrawer = false">
        <div class="absolute inset-0 bg-black/40" @click="ui.sidebarDrawer = false" />
        <div class="relative flex h-full w-full max-w-[320px] flex-col bg-[var(--cs-bg)] p-3 shadow-2xl sm:rounded-r-[28px]">
          <ConversationSidebar class="min-h-0 flex-1" :current-id="id" drawer @close="ui.sidebarDrawer = false" />
        </div>
      </div>
      <div v-if="!wide && ui.dashboardDrawer" class="fixed inset-0 z-50 flex justify-end" @keydown.escape="ui.dashboardDrawer = false">
        <div class="absolute inset-0 bg-black/40" @click="ui.dashboardDrawer = false" />
        <div class="relative flex h-full w-full flex-col bg-[var(--cs-bg)] p-4 shadow-2xl sm:max-w-[400px] sm:rounded-l-[28px]">
          <TaskDashboard class="min-h-0 flex-1" closable @close="ui.dashboardDrawer = false" />
        </div>
      </div>
    </Teleport>
    <BrowserModal />
  </div>
</template>

<style scoped>
.drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  border-radius: 28px;
  background-color: color-mix(in srgb, var(--cs-bg) 78%, transparent);
  pointer-events: none;
}
.drop-box {
  display: flex;
  width: 100%;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: 2px dashed var(--pastel-mint-dot);
  border-radius: 24px;
  background-color: var(--pastel-mint);
  color: var(--pastel-mint-ink);
  text-align: center;
}
</style>
