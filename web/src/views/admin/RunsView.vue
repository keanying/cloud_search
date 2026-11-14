<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleAlert } from 'lucide-vue-next'
import type { AdminAgentRun } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import FilterSelect from '@/components/admin/FilterSelect.vue'
import RunDrawer from '@/components/admin/RunDrawer.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import TableToolbar from '@/components/admin/TableToolbar.vue'
import TaskDrawer from '@/components/admin/TaskDrawer.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import { compact, duration, money, runStatus } from '@/lib/adminFormat'
import { formatTime } from '@/lib/format'
import { useColumnPrefs } from '@/lib/useColumnPrefs'
import { useServerTable } from '@/lib/useServerTable'

/** 调用记录：每次智能体模型调用；点行看详情（完整错误、token、费用），可跳到所属任务 */
const route = useRoute()
const router = useRouter()
const qv = (k: string) => (typeof route.query[k] === 'string' ? (route.query[k] as string) : '')

const ROLES = [
  { value: 'requirement_compiler', label: '需求编译' },
  { value: 'search_planner', label: '搜索规划' },
  { value: 'browser_researcher', label: '浏览研究' },
  { value: 'extractor', label: '信息抽取' },
  { value: 'coordinator', label: '协调' },
  { value: 'verifier', label: '核验' },
  { value: 'analyst', label: '分析' },
  { value: 'report_writer', label: '报告写作' },
]
const STATUS = [
  { value: 'succeeded', label: '成功', dot: 'var(--pastel-mint-dot)' },
  { value: 'failed', label: '失败（含被拒、取消）', dot: 'var(--pastel-peach-dot)' },
]

const t = useServerTable<AdminAgentRun, { q: string; role: string; status: string }>((q) => api.adminRuns(q), {
  q: qv('q'),
  role: qv('role'),
  status: qv('status'),
})
watch(
  () => ({ ...t.filters }),
  (f) => void router.replace({ query: { ...route.query, q: f.q || undefined, role: f.role || undefined, status: f.status || undefined } }),
)

const all: Column[] = [
  { key: 'started_time', title: '时间', width: 160, fixed: 'left' },
  { key: 'agent_role', title: '智能体', width: 150 },
  { key: 'model', title: '模型', minWidth: 220 },
  { key: 'run_status', title: '状态', width: 110 },
  { key: 'duration_ms', title: '耗时', width: 90, align: 'right' },
  { key: 'tokens', title: 'Token 入 / 出', width: 140, align: 'right' },
  { key: 'cost', title: '费用', width: 100, align: 'right' },
  { key: 'task_id', title: '任务', width: 170 },
]
const cols = useColumnPrefs('admin-runs', all)
const current = ref<AdminAgentRun | null>(null)
const taskOpen = ref<string | null>(null)
const activeKey = computed(() => current.value?.agent_run_id ?? null)
</script>

<template>
  <AdminPage>
    <TableToolbar
      v-model:q="t.filters.q"
      v-model:hidden="cols.hidden.value"
      v-model:density="cols.density.value"
      placeholder="搜索模型、供应方、任务 ID"
      :loading="t.loading.value"
      :toggleable="cols.toggleable.value"
      @refresh="t.reload()"
    >
      <FilterSelect v-model="t.filters.role" label="智能体" :options="ROLES" />
      <FilterSelect v-model="t.filters.status" label="状态" :options="STATUS" />
    </TableToolbar>
    <DataTable
      v-model:page="t.page.value"
      v-model:size="t.size.value"
      :columns="cols.visible.value"
      :rows="t.rows.value"
      row-key="agent_run_id"
      :total="t.total.value"
      :loading="t.loading.value"
      :density="cols.density.value"
      :active-key="activeKey"
      row-clickable
      empty-text="还没有模型调用记录"
      empty-desc="智能体每次调用大模型都会记录在这里"
      @row-click="(r: AdminAgentRun) => (current = r)"
    >
      <template #cell-started_time="{ row }"><span class="text-slate-300 tabular-nums">{{ formatTime(row.started_time) }}</span></template>
      <template #cell-agent_role="{ row }">
        <div class="leading-tight">
          <div class="font-medium text-white">{{ row.role_label }}</div>
          <div class="font-mono text-[11px] text-slate-500">{{ row.agent_role }}</div>
        </div>
      </template>
      <template #cell-model="{ row }">
        <div class="leading-tight">
          <div class="truncate text-slate-100">{{ row.model_name || '—' }}</div>
          <div class="text-[11px] text-slate-500">{{ row.provider_name || '' }}<template v-if="row.request_qty > 1"> · {{ row.request_qty }} 次请求</template></div>
        </div>
      </template>
      <template #cell-run_status="{ row }">
        <span class="inline-flex items-center gap-1">
          <StatusPill :tone="runStatus(row.run_status).tone" :text="runStatus(row.run_status).label" />
          <CircleAlert v-if="row.error_desc" class="h-3.5 w-3.5 text-rose-300" :title="row.error_desc" />
        </span>
      </template>
      <template #cell-duration_ms="{ row }"><span class="tabular-nums">{{ duration(row.duration_ms) }}</span></template>
      <template #cell-tokens="{ row }">
        <span class="tabular-nums text-slate-200">{{ compact(row.input_token_qty) }}</span>
        <span class="mx-1 text-slate-500">/</span>
        <span class="tabular-nums text-slate-200">{{ compact(row.output_token_qty) }}</span>
      </template>
      <template #cell-cost="{ row }">
        <span v-if="row.cost_status === 'unknown'" class="text-[12px] text-amber-300" title="单价未知，未计入费用">待核算</span>
        <span v-else class="tabular-nums">{{ money(row.cost_minor_amt, row.currency_code) }}</span>
      </template>
      <template #cell-task_id="{ row }">
        <button
          v-if="row.task_id"
          type="button"
          class="truncate font-mono text-[11px] text-slate-400 hover:text-white hover:underline"
          :title="`查看任务 ${row.task_id}`"
          @click.stop="taskOpen = row.task_id"
        >{{ row.task_id }}</button>
        <span v-else class="text-[12px] text-slate-500">对话轮次</span>
      </template>
    </DataTable>

    <RunDrawer :run="current" @close="current = null" @open-task="(id: string) => ((current = null), (taskOpen = id))" />
    <TaskDrawer :task-id="taskOpen" @close="taskOpen = null" />
  </AdminPage>
</template>
