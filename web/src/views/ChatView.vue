<script setup lang="ts">
import { computed, onBeforeUnmount, provide, ref, watch } from 'vue'
import { Loader2, WifiOff } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import MessageList from '@/components/chat/MessageList.vue'
import RightPanel from '@/components/panel/RightPanel.vue'
import { ChatActionsKey } from '@/lib/chatActions'
import { taskStatusLabel } from '@/lib/format'
import { useChatStore } from '@/stores/chat'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ id: string }>()
const chat = useChatStore()
const panel = usePanelStore()
const toast = useToastStore()

const text = ref('')
const mode = ref<ModeSelection>('auto')
const hint = ref<string | null>(null)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
const list = ref<InstanceType<typeof MessageList> | null>(null)
const stopSubmitting = ref(false)

provide(ChatActionsKey, {
  focusComposer(h?: string) {
    hint.value = h ?? null
    composer.value?.focus()
  },
})

watch(
  () => props.id,
  async (id) => {
    panel.reset()
    text.value = ''
    hint.value = null
    await chat.open(id)
    list.value?.scrollToBottom(false)
  },
  { immediate: true },
)

// 离开页面只关闭事件订阅，不停止任何云端任务
onBeforeUnmount(() => chat.close())

async function submit() {
  const t = text.value.trim()
  if (!t) return
  try {
    await chat.send(t, mode.value)
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
  <div class="flex h-full" data-split>
    <section class="flex min-w-0 flex-1 flex-col">
      <div
        v-if="chat.streamStatus === 'reconnecting'"
        class="mx-auto mt-2 flex items-center gap-2 rounded-full bg-amber-500/15 px-3 py-1 text-xs text-amber-200"
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

      <div class="mx-auto w-full max-w-3xl px-4 pb-4 md:px-6">
        <div v-if="chat.hasActive" class="mb-1.5 truncate px-1 text-xs text-slate-500" :title="activeLabel">
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
          :stopping="chat.isStopping || stopSubmitting"
          stop-hint="停止最近一轮关联的任务；已提交成果会保留"
          @submit="submit"
          @stop="stopTurn"
        />
      </div>
    </section>
    <RightPanel />
  </div>
</template>
