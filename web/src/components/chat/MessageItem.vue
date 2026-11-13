<script setup lang="ts">
import { computed } from 'vue'
import { UserRound } from 'lucide-vue-next'
import type { MessageOut } from '@/api/types'
import BrandLogo from '@/components/common/BrandLogo.vue'
import MessagePartView from '@/components/parts/MessagePartView.vue'
import AnswerToolbar from './AnswerToolbar.vue'
import { modeLabel } from '@/lib/format'

const props = defineProps<{ message: MessageOut }>()

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
  <div v-if="message.role === 'user'" class="flex justify-end gap-3">
    <div class="max-w-[80%]">
      <div class="rounded-2xl rounded-tr-md bg-gradient-to-b from-brand-500 to-brand-600 px-4 py-2.5 text-[15px] leading-6 whitespace-pre-wrap text-snow shadow-md shadow-brand-600/20">
        {{ userText }}
      </div>
      <div v-if="message.mode_selection && message.mode_selection !== 'auto'" class="mt-1 text-right text-xs text-slate-500">
        {{ modeLabel(message.mode_selection) }}
      </div>
    </div>
    <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/10" aria-hidden="true">
      <UserRound class="h-5 w-5" />
    </div>
  </div>

  <div v-else class="flex gap-3">
    <div class="shrink-0" aria-hidden="true"><BrandLogo :size="36" /></div>
    <div class="min-w-0 flex-1 space-y-3">
      <div v-if="pending && !message.parts.length" class="flex items-center gap-2 py-2 text-sm text-slate-400" aria-live="polite">
        <span class="flex gap-1">
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300 [animation-delay:-0.3s]" />
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300 [animation-delay:-0.15s]" />
          <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-300" />
        </span>
        正在理解你的需求…
      </div>
      <template v-for="(p, i) in message.parts" :key="p.part_id">
        <div v-if="p.type === 'text'" class="surface rounded-tl-md px-5 py-4">
          <MessagePartView :part="p" :task-id="citeTaskId" :streaming="pending && i === message.parts.length - 1" />
          <AnswerToolbar v-if="p.part_id.startsWith('answer-') && !pending" :message="message" :part="p" />
        </div>
        <MessagePartView v-else :part="p" :task-id="citeTaskId" />
      </template>
      <div v-if="message.message_status === 'error' && !message.parts.some((p) => p.type === 'error')" class="text-sm text-rose-300">
        回复生成失败，请重试。
      </div>
    </div>
  </div>
</template>
