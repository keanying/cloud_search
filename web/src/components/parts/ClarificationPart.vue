<script setup lang="ts">
import { HelpCircle } from 'lucide-vue-next'
import type { ClarificationPart } from '@/api/types'
import { useChatActions } from '@/lib/chatActions'

defineProps<{ part: ClarificationPart }>()
const actions = useChatActions()
</script>

<template>
  <div class="glass p-4">
    <div class="card-title mb-2"><HelpCircle class="h-4 w-4 text-amber-300" /> 需要你补充几点</div>
    <ol class="list-decimal space-y-1 pl-5 text-sm text-slate-200">
      <li v-for="(q, i) in part.questions" :key="i">{{ q }}</li>
    </ol>
    <button class="btn-secondary btn-sm mt-3" @click="actions.focusComposer('请直接在下方回复补充信息')">回复补充</button>
  </div>
</template>
