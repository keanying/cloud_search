<script setup lang="ts">
import { MessageCircleQuestion } from 'lucide-vue-next'
import type { ClarificationPart } from '@/api/types'
import { useChatActions } from '@/lib/chatActions'

defineProps<{ part: ClarificationPart }>()
const actions = useChatActions()
</script>

<template>
  <div class="surface p-5">
    <div class="flex items-center gap-2">
      <span class="flex h-9 w-9 items-center justify-center rounded-full card-butter">
        <MessageCircleQuestion class="h-4 w-4 accent-ink" />
      </span>
      <span class="card-title">需要你补充几点</span>
      <span class="pill card-butter accent-ink ml-auto">✋ 需要你</span>
    </div>
    <ul class="mt-3 flex flex-col gap-2">
      <li v-for="(q, i) in part.questions" :key="i">
        <button
          type="button"
          class="sunken hairline flex w-full items-start gap-2.5 rounded-2xl border px-3.5 py-2.5 text-left text-sm text-slate-100 transition-colors hover:border-slate-400"
          @click="actions.focusComposer(`回答：${q}`)"
        >
          <span class="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--cs-ink)] text-[11px] font-bold text-[var(--cs-on-ink)]">{{ i + 1 }}</span>
          <span>{{ q }}</span>
        </button>
      </li>
    </ul>
    <button class="btn-primary btn-sm mt-4" @click="actions.focusComposer('请直接在下方回复补充信息')">回复补充</button>
  </div>
</template>
