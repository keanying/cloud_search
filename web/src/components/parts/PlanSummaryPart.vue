<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, ClipboardList, Loader2 } from 'lucide-vue-next'
import type { PlanSummaryPart } from '@/api/types'
import { api } from '@/api/client'
import { modeLabel } from '@/lib/format'
import { useChatActions } from '@/lib/chatActions'
import { useChatStore } from '@/stores/chat'
import { useToastStore } from '@/stores/toast'
import StatusBadge from '@/components/common/StatusBadge.vue'

const props = defineProps<{ part: PlanSummaryPart }>()
const chat = useChatStore()
const toast = useToastStore()
const actions = useChatActions()
const confirming = ref(false)
const showFields = ref(true)

const task = computed(() => chat.tasks[props.part.task_id])
/** 以后端任务真实状态为准：任务已离开草稿即视为已确认 */
const effectiveStatus = computed(() => {
  if (props.part.status !== 'awaiting_confirmation') return props.part.status
  if (task.value && task.value.task_status !== 'draft') return 'confirmed'
  return 'awaiting_confirmation'
})
/** 计划已被修订（hash 变化）时旧确认失效 */
const planOutdated = computed(
  () => !!task.value?.plan_hash && task.value.plan_hash !== props.part.plan_hash && effectiveStatus.value === 'awaiting_confirmation',
)

const badge = computed(() => {
  switch (effectiveStatus.value) {
    case 'confirmed':
      return { text: '已确认', tone: 'success' as const }
    case 'auto_started':
      return { text: '已自动开始', tone: 'info' as const }
    default:
      return { text: '等待确认', tone: 'warning' as const }
  }
})

async function confirm() {
  confirming.value = true
  try {
    chat.upsertTask(await api.confirmTask(props.part.task_id, props.part.plan_hash))
  } catch (e) {
    toast.error(e, '确认失败')
    void chat.refreshTask(props.part.task_id)
  } finally {
    confirming.value = false
  }
}
</script>

<template>
  <div class="glass p-4">
    <div class="flex items-start gap-3">
      <ClipboardList class="mt-0.5 h-5 w-5 shrink-0 text-brand-300" />
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="text-base font-semibold text-white">{{ part.title }}</h3>
          <StatusBadge tone="neutral">{{ modeLabel(part.mode) }}</StatusBadge>
          <div class="flex-1" />
          <StatusBadge :tone="badge.tone">{{ badge.text }}</StatusBadge>
        </div>
        <p v-if="part.summary" class="mt-1 text-sm text-slate-300">{{ part.summary }}</p>
      </div>
    </div>

    <ol v-if="part.steps?.length" class="mt-3 space-y-2">
      <li v-for="(s, i) in part.steps" :key="i" class="flex items-start gap-3 text-sm text-slate-200">
        <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/5 text-xs">
          {{ i + 1 }}
        </span>
        <span class="pt-0.5">{{ s }}</span>
      </li>
    </ol>

    <div v-if="part.limits && (part.limits.max_queries || part.limits.max_sources)" class="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
      <span v-if="part.limits.max_queries" class="rounded-md bg-white/5 px-2 py-1">最多 {{ part.limits.max_queries }} 次搜索</span>
      <span v-if="part.limits.max_sources" class="rounded-md bg-white/5 px-2 py-1">最多读取 {{ part.limits.max_sources }} 个来源</span>
    </div>

    <div v-if="part.fields?.length" class="mt-3">
      <button class="flex items-center gap-1 text-xs text-slate-400 hover:text-white" :aria-expanded="showFields" @click="showFields = !showFields">
        <ChevronDown class="h-3.5 w-3.5 transition" :class="showFields ? '' : '-rotate-90'" />
        字段（{{ part.fields.length }}）
      </button>
      <div v-if="showFields" class="mt-2 overflow-x-auto rounded-xl border border-white/10">
        <table class="w-full text-left text-sm">
          <thead class="bg-white/5 text-xs text-slate-400">
            <tr>
              <th class="px-3 py-1.5 font-medium">字段</th>
              <th class="px-3 py-1.5 font-medium">键</th>
              <th class="px-3 py-1.5 font-medium">类型</th>
              <th class="px-3 py-1.5 font-medium">必填</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in part.fields" :key="f.key" class="border-t border-white/5">
              <td class="px-3 py-1.5 text-slate-100">{{ f.label }}</td>
              <td class="px-3 py-1.5 font-mono text-xs text-slate-400">{{ f.key }}</td>
              <td class="px-3 py-1.5 text-slate-300">{{ f.type }}</td>
              <td class="px-3 py-1.5 text-slate-300">{{ f.required ? '是' : '否' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <p v-if="planOutdated" class="mt-3 text-xs text-amber-300">计划已更新，此版本的确认已失效，请查看最新计划。</p>

    <div v-if="effectiveStatus === 'awaiting_confirmation'" class="mt-4 flex flex-wrap gap-2">
      <button class="btn-primary" :disabled="confirming || planOutdated" @click="confirm">
        <Loader2 v-if="confirming" class="h-4 w-4 animate-spin" />
        确认计划
      </button>
      <button class="btn-secondary" @click="actions.focusComposer('用自然语言说明要调整的范围、字段或数量上限，修改后需重新确认')">
        调整范围
      </button>
    </div>
  </div>
</template>
