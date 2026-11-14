<script setup lang="ts">
import { useRouter } from 'vue-router'
import { RefreshCw } from 'lucide-vue-next'
import type { AdminTask } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import ChipSelect from '@/components/common/ChipSelect.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import { TASK_MODE_FILTER, TASK_STATUS_FILTER, compact, hueTone, money, taskPastel } from '@/lib/adminFormat'
import { formatTime, modeLabel, relativeTime, taskStatusLabel } from '@/lib/format'
import { useServerTable } from '@/lib/useServerTable'

const router = useRouter()
const t = useServerTable<AdminTask, { q: string; status: string; mode: string }>(
  (q) => api.adminTasks(q),
  { q: '', status: '', mode: '' },
)

const columns: Column[] = [
  { key: 'title', title: '任务', minWidth: 300, fixed: 'left', width: 340 },
  { key: 'task_status', title: '状态', width: 130 },
  { key: 'mode', title: '模式', width: 110 },
  { key: 'user', title: '发起人', width: 170 },
  { key: 'llm_request_qty', title: '模型调用', width: 110, align: 'right' },
  { key: 'spent_minor_amt', title: '费用', width: 120, align: 'right' },
  { key: 'created_time', title: '创建时间', width: 170 },
  { key: 'updated_time', title: '最近更新', width: 120 },
]

function open(row: AdminTask) {
  if (row.conversation_id) void router.push({ name: 'chat', params: { id: row.conversation_id } })
}
</script>

<template>
  <AdminPage>
    <template #actions>
      <button class="btn-secondary btn-sm" :disabled="t.loading.value" @click="t.reload()">
        <RefreshCw class="h-3.5 w-3.5" :class="t.loading.value ? 'animate-spin' : ''" /> 刷新
      </button>
    </template>
    <FilterBar v-model:q="t.filters.q" placeholder="搜索任务标题、用户名">
      <ChipSelect v-model="t.filters.status" label="状态" :options="TASK_STATUS_FILTER" />
      <ChipSelect v-model="t.filters.mode" label="模式" :options="TASK_MODE_FILTER" />
    </FilterBar>
    <DataTable
      v-model:page="t.page.value"
      v-model:size="t.size.value"
      :columns="columns"
      :rows="t.rows.value"
      row-key="task_id"
      :total="t.total.value"
      :loading="t.loading.value"
      row-clickable
      show-density
      empty-text="没有符合条件的任务"
      @row-click="open"
    >
      <template #cell-title="{ row }">
        <div class="min-w-0">
          <div class="truncate font-semibold text-white" :title="row.title">{{ row.title }}</div>
          <div class="mt-0.5 truncate font-mono text-[11px] text-slate-500">{{ row.task_id }}</div>
        </div>
      </template>
      <template #cell-task_status="{ row }">
        <StatusPill :tone="taskPastel(row.task_status)" :text="taskStatusLabel(row.task_status, row.status_reason)" />
      </template>
      <template #cell-mode="{ row }">
        <span class="text-slate-300">{{ modeLabel(row.mode) }}</span>
      </template>
      <template #cell-user="{ row }">
        <span class="flex items-center gap-2">
          <span
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold"
            :style="{ background: `var(--pastel-${hueTone(row.username ?? '?')})`, color: `var(--pastel-${hueTone(row.username ?? '?')}-ink)` }"
          >
            {{ (row.display_name || row.username || '?').slice(0, 1).toUpperCase() }}
          </span>
          <span class="truncate text-slate-200">{{ row.display_name || row.username || '—' }}</span>
        </span>
      </template>
      <template #cell-llm_request_qty="{ row }"><span class="tabular-nums">{{ compact(row.llm_request_qty) }}</span></template>
      <template #cell-spent_minor_amt="{ row }">
        <span class="tabular-nums">{{ money(row.spent_minor_amt, 'CNY') }}</span>
        <span v-if="row.cost_unknown_qty" class="ml-1 text-[11px] text-amber-300" :title="`${row.cost_unknown_qty} 次调用单价未知，未计入`">+?</span>
      </template>
      <template #cell-created_time="{ row }"><span class="text-slate-300 tabular-nums">{{ formatTime(row.created_time) }}</span></template>
      <template #cell-updated_time="{ row }"><span class="text-slate-400">{{ relativeTime(row.updated_time) }}</span></template>
    </DataTable>
  </AdminPage>
</template>
