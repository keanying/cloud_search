<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { AdminTask } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import FilterSelect from '@/components/admin/FilterSelect.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import TableToolbar from '@/components/admin/TableToolbar.vue'
import TaskDrawer from '@/components/admin/TaskDrawer.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import { TASK_MODE_FILTER, compact, hueTone, money, taskPastel } from '@/lib/adminFormat'
import { formatTime, modeLabel, relativeTime, taskStatusLabel } from '@/lib/format'
import { useColumnPrefs } from '@/lib/useColumnPrefs'
import { useServerTable } from '@/lib/useServerTable'

/** 任务：服务端分页 + 筛选；点行在右侧打开详情（地址栏 ?task= 可直达） */
const route = useRoute()
const router = useRouter()
const qv = (k: string) => (typeof route.query[k] === 'string' ? (route.query[k] as string) : '')
const t = useServerTable<AdminTask, { q: string; status: string; mode: string }>((q) => api.adminTasks(q), {
  q: qv('q'),
  status: qv('status'),
  mode: qv('mode'),
})

const STATUS = [
  { value: 'active', label: '进行中', dot: 'var(--pastel-sky-dot)' },
  { value: 'completed', label: '执行结束', dot: 'var(--pastel-mint-dot)' },
  { value: 'failed', label: '失败', dot: 'var(--pastel-peach-dot)' },
  { value: 'stopped', label: '已停止', dot: 'var(--pastel-butter-dot)' },
  { value: 'draft', label: '草稿', dot: 'var(--color-slate-500)' },
]

const all: Column[] = [
  { key: 'title', title: '任务', minWidth: 300, fixed: 'left', width: 360 },
  { key: 'task_status', title: '状态', width: 120 },
  { key: 'mode', title: '模式', width: 100 },
  { key: 'user', title: '发起人', width: 150 },
  { key: 'llm_request_qty', title: '模型调用', width: 96, align: 'right' },
  { key: 'spent_minor_amt', title: '费用', width: 100, align: 'right' },
  { key: 'created_time', title: '创建时间', width: 160 },
  { key: 'updated_time', title: '最近更新', width: 110 },
]
const cols = useColumnPrefs('admin-tasks', all, ['title'])

const openId = computed(() => qv('task') || null)
function openTask(id: string | null) {
  void router.replace({ query: { ...route.query, task: id || undefined } })
}
watch(
  () => ({ ...t.filters }),
  (f) => void router.replace({ query: { ...route.query, q: f.q || undefined, status: f.status || undefined, mode: f.mode || undefined } }),
)
</script>

<template>
  <AdminPage>
    <TableToolbar
      v-model:q="t.filters.q"
      v-model:hidden="cols.hidden.value"
      v-model:density="cols.density.value"
      placeholder="搜索标题、任务 ID、用户名"
      :loading="t.loading.value"
      :toggleable="cols.toggleable.value"
      @refresh="t.reload()"
    >
      <FilterSelect v-model="t.filters.status" label="状态" :options="STATUS" />
      <FilterSelect v-model="t.filters.mode" label="模式" :options="TASK_MODE_FILTER" />
    </TableToolbar>
    <DataTable
      v-model:page="t.page.value"
      v-model:size="t.size.value"
      :columns="cols.visible.value"
      :rows="t.rows.value"
      row-key="task_id"
      :total="t.total.value"
      :loading="t.loading.value"
      :density="cols.density.value"
      :active-key="openId"
      row-clickable
      empty-text="没有符合条件的任务"
      @row-click="(r: AdminTask) => openTask(r.task_id)"
    >
      <template #cell-title="{ row }">
        <div class="min-w-0">
          <div class="truncate font-medium text-white" :title="row.title">{{ row.title }}</div>
          <div class="mt-0.5 truncate font-mono text-[11px] text-slate-500">{{ row.task_id }}</div>
        </div>
      </template>
      <template #cell-task_status="{ row }">
        <StatusPill :tone="taskPastel(row.task_status)" :text="taskStatusLabel(row.task_status, row.status_reason)" />
      </template>
      <template #cell-mode="{ row }"><span class="text-slate-300">{{ modeLabel(row.mode) }}</span></template>
      <template #cell-user="{ row }">
        <span class="flex items-center gap-2">
          <span
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
            :style="{ background: `var(--pastel-${hueTone(row.username ?? '?')})`, color: `var(--pastel-${hueTone(row.username ?? '?')}-ink)` }"
          >{{ (row.display_name || row.username || '?').slice(0, 1).toUpperCase() }}</span>
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

    <TaskDrawer :task-id="openId" @close="openTask(null)" />
  </AdminPage>
</template>
