<script setup lang="ts">
import { computed } from 'vue'
import type { MessageOut } from '@/api/types'
import BrandLogo from '@/components/common/BrandLogo.vue'
import MessagePartView from '@/components/parts/MessagePartView.vue'
import AnswerToolbar from './AnswerToolbar.vue'
import { modeLabel } from '@/lib/format'

const props = defineProps<{ message: MessageOut; latest?: boolean }>()

const userText = computed(() =>
  props.message.parts
    .filter((p) => p.type === 'text')
    .map((p) => (p as { text: string }).text)
    .join('\n'),
)
/** 引用标记对应的任务：优先 source 片段上的 task，否则消息绑定的首个任务 */
const citeTaskId = computed(() => {
  const sp = props.message.parts.find((p) => p.type === 'source') as { task_id?: string } | undefined
  return sp?.task_id ?? props.message.task_ids[0] ?? null
})
const pending = computed(() => props.message.message_status === 'pending')
</script>

<template>
  <div v-if="message.role === 'user'" class="flex justify-end">
    <div class="max-w-[82%]">
      <div class="user-bubble rounded-[26px] rounded-br-lg px-5 py-3 text-[16px] leading-7 whitespace-pre-wrap">
        {{ userText }}
      </div>
      <div v-if="message.mode_selection && message.mode_selection !== 'auto'" class="mt-1.5 flex justify-end">
        <span class="pill sunken hairline border text-slate-400">{{ modeLabel(message.mode_selection) }}</span>
      </div>
    </div>
  </div>

  <div v-else class="flex gap-3">
    <div class="hidden shrink-0 sm:block" aria-hidden="true"><BrandLogo :size="36" /></div>
    <div class="min-w-0 flex-1 space-y-4">
      <div v-if="pending && !message.parts.length" class="flex items-center gap-2 py-2 text-sm text-slate-400" aria-live="polite">
        <span class="flex gap-1">
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
        </span>
        正在理解你的需求…
      </div>
      <template v-for="(p, i) in message.parts" :key="p.part_id">
        <div v-if="p.type === 'text'" class="surface rounded-tl-lg px-6 py-5">
          <MessagePartView :part="p" :task-id="citeTaskId" :streaming="pending && i === message.parts.length - 1" />
          <AnswerToolbar v-if="p.part_id.startsWith('answer-') && !pending" :message="message" :part="p" />
        </div>
        <!-- “接着问”只在最新一条回答下显示，避免历史消息堆满按钮 -->
        <MessagePartView v-else-if="p.type !== 'suggestions' || latest" :part="p" :task-id="citeTaskId" />
      </template>
      <div v-if="message.message_status === 'error' && !message.parts.some((p) => p.type === 'error')" class="text-sm text-rose-300">
        回复生成失败，请重试。
      </div>
    </div>
  </div>
</template>

<style scoped>
.user-bubble {
  background-color: var(--cs-ink);
  color: var(--cs-on-ink);
}
</style>
