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
      return { text: '已确认', tone: 'success' as const, emoji: '✅' }
    case 'auto_started':
      return { text: '已自动开始', tone: 'info' as const, emoji: '⏳' }
    default:
      return { text: '需要你确认', tone: 'warning' as const, emoji: '✋' }
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
  <div class="card-lilac p-5">
    <div class="flex items-start gap-3">
      <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--cs-surface-solid)]">
        <ClipboardList class="h-4 w-4 accent-ink" />
      </span>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs font-bold tracking-wide accent-ink">执行计划</span>
          <span class="pill bg-[var(--cs-surface-solid)] text-slate-200">{{ modeLabel(part.mode) }}</span>
          <div class="flex-1" />
          <StatusBadge :tone="badge.tone" :emoji="badge.emoji">{{ badge.text }}</StatusBadge>
        </div>
        <h3 class="mt-1 text-[17px] leading-6 font-bold tracking-tight text-white">{{ part.title }}</h3>
        <p v-if="part.summary" class="mt-1 text-sm text-slate-200">{{ part.summary }}</p>
      </div>
    </div>

    <ol v-if="part.steps?.length" class="tile mt-4 space-y-2.5 p-3.5">
      <li v-for="(s, i) in part.steps" :key="i" class="flex items-start gap-3 text-sm text-slate-100">
        <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full accent-dot text-xs font-bold text-snow">
          {{ i + 1 }}
        </span>
        <span class="pt-0.5">{{ s }}</span>
      </li>
    </ol>

    <div v-if="part.limits && (part.limits.max_queries || part.limits.max_sources)" class="mt-3 flex flex-wrap gap-2 text-xs">
      <span v-if="part.limits.max_queries" class="pill bg-[var(--cs-surface-solid)] text-slate-300">🔎 最多 {{ part.limits.max_queries }} 次搜索</span>
      <span v-if="part.limits.max_sources" class="pill bg-[var(--cs-surface-solid)] text-slate-300">📄 最多读取 {{ part.limits.max_sources }} 个来源</span>
    </div>

    <div v-if="part.fields?.length" class="mt-3">
      <button class="flex items-center gap-1 text-xs font-semibold text-slate-300 hover:text-white" :aria-expanded="showFields" @click="showFields = !showFields">
        <ChevronDown class="h-3.5 w-3.5 transition" :class="showFields ? '' : '-rotate-90'" />
        字段（{{ part.fields.length }}）
      </button>
      <div v-if="showFields" class="mt-2 overflow-x-auto rounded-2xl bg-[var(--cs-surface-solid)]">
        <table class="w-full text-left text-sm">
          <thead class="text-xs text-slate-400">
            <tr>
              <th class="px-3 py-2 font-semibold">字段</th>
              <th class="px-3 py-2 font-semibold">键</th>
              <th class="px-3 py-2 font-semibold">类型</th>
              <th class="px-3 py-2 font-semibold">必填</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in part.fields" :key="f.key" class="hairline border-t">
              <td class="px-3 py-2 text-slate-100">{{ f.label }}</td>
              <td class="px-3 py-2 font-mono text-xs text-slate-400">{{ f.key }}</td>
              <td class="px-3 py-2 text-slate-300">{{ f.type }}</td>
              <td class="px-3 py-2 text-slate-300">{{ f.required ? '是' : '否' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <p v-if="planOutdated" class="mt-3 text-xs font-medium text-amber-200">计划已更新，此版本的确认已失效，请查看最新计划。</p>

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
