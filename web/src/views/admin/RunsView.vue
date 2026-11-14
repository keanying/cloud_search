<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { CircleAlert, MessageSquare, RefreshCw } from 'lucide-vue-next'
import type { AdminAgentRun } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import ChipSelect from '@/components/common/ChipSelect.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import { RUN_STATUS, compact, duration, money, runStatus } from '@/lib/adminFormat'
import { formatTime } from '@/lib/format'
import { useServerTable } from '@/lib/useServerTable'

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
const STATUS = computed(() =>
  Object.entries(RUN_STATUS)
    .filter(([k]) => k !== 'running')
    .map(([value, v]) => ({
      value,
      label: v.label,
      dot: v.tone === 'gray' ? 'var(--color-slate-500)' : `var(--pastel-${v.tone}-dot)`,
    })),
)

const t = useServerTable<AdminAgentRun, { q: string; role: string; status: string }>(
  (q) => api.adminRuns(q),
  { q: '', role: '', status: '' },
)

const columns: Column[] = [
  { key: 'started_time', title: '时间', width: 170, fixed: 'left' },
  { key: 'agent_role', title: '智能体', width: 150 },
  { key: 'model', title: '模型', minWidth: 220 },
  { key: 'run_status', title: '状态', width: 120 },
  { key: 'duration_ms', title: '耗时', width: 100, align: 'right' },
  { key: 'tokens', title: 'Token（入 / 出）', width: 170, align: 'right' },
  { key: 'cost', title: '费用', width: 110, align: 'right' },
  { key: 'task', title: '所属', width: 90, align: 'center' },
]
</script>

<template>
  <AdminPage>
    <template #actions>
      <button class="btn-secondary btn-sm" :disabled="t.loading.value" @click="t.reload()">
        <RefreshCw class="h-3.5 w-3.5" :class="t.loading.value ? 'animate-spin' : ''" /> 刷新
      </button>
    </template>
    <FilterBar v-model:q="t.filters.q" placeholder="搜索模型名、任务 ID、错误信息">
      <ChipSelect v-model="t.filters.status" label="状态" :options="STATUS" />
    </FilterBar>
    <div class="-mt-1 mb-4"><ChipSelect v-model="t.filters.role" label="智能体" :options="ROLES" /></div>
    <DataTable
      v-model:page="t.page.value"
      v-model:size="t.size.value"
      :columns="columns"
      :rows="t.rows.value"
      row-key="agent_run_id"
      :total="t.total.value"
      :loading="t.loading.value"
      show-density
      empty-text="还没有模型调用记录"
      empty-desc="智能体每次调用大模型都会记录在这里"
    >
      <template #cell-started_time="{ row }"><span class="text-slate-300 tabular-nums">{{ formatTime(row.started_time) }}</span></template>
      <template #cell-agent_role="{ row }">
        <div class="leading-tight">
          <div class="font-semibold text-white">{{ row.role_label }}</div>
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
          <StatusPill :tone="runStatus(row.run_status).tone" :text="runStatus(row.run_status).label" :title="row.error_desc ?? undefined" />
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
        <span v-if="row.cost_status === 'unknown'" class="text-xs text-amber-300" title="单价未知，未计入费用">待核算</span>
        <span v-else class="tabular-nums">{{ money(row.cost_minor_amt, row.currency_code) }}</span>
      </template>
      <template #cell-task="{ row }">
        <RouterLink
          v-if="row.conversation_id"
          :to="{ name: 'chat', params: { id: row.conversation_id } }"
          class="icon-btn !h-8 !w-8"
          :title="row.task_id ? `任务 ${row.task_id}` : '打开对话'"
          aria-label="打开对话"
        >
          <MessageSquare class="h-4 w-4" />
        </RouterLink>
        <span v-else class="text-slate-500">—</span>
      </template>
    </DataTable>
  </AdminPage>
</template>
