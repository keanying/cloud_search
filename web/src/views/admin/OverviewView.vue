<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Activity, ArrowRight, Coins, FileText, Hash, ListChecks, RefreshCw, Users } from 'lucide-vue-next'
import type { AdminOverview } from '@/api/types'
import { api } from '@/api/client'
import AdminChart from '@/components/admin/AdminChart.vue'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import TaskDrawer from '@/components/admin/TaskDrawer.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
import { compact, money } from '@/lib/adminFormat'
import { relativeTime } from '@/lib/format'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const days = ref<7 | 14 | 30>(14)
const data = ref<AdminOverview | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await api.adminOverview(days.value)
  } catch (e) {
    toast.error(e, '加载概览失败')
  } finally {
    loading.value = false
  }
}
watch(days, load, { immediate: true })

const range = computed(() => {
  const d = data.value?.tasks_by_day ?? []
  const total = d.reduce((a, x) => a + x.total, 0)
  const completed = d.reduce((a, x) => a + x.completed, 0)
  const failed = d.reduce((a, x) => a + x.failed, 0)
  return { total, completed, failed }
})
const dayMax = computed(() => Math.max(1, ...(data.value?.tasks_by_day ?? []).map((d) => d.total)))
const llm = computed(() => data.value?.llm)
const successRate = computed(() => {
  const l = llm.value
  if (!l || !l.requests) return null
  return Math.max(0, 1 - l.failed_runs / l.requests)
})
const router = useRouter()
const taskOpen = ref<string | null>(null)
const costText = computed(() => {
  const c = llm.value?.cost ?? []
  return c.length ? c.map((x) => money(x.minor_amt, x.currency_code)).join(' + ') : '—'
})
const kpis = computed(() => {
  const t = data.value?.totals
  const l = llm.value
  const done = range.value.total ? Math.round((range.value.completed / range.value.total) * 100) : null
  return [
    {
      key: 'tasks', label: `近 ${days.value} 天任务`, icon: ListChecks, tone: 'peach',
      value: data.value ? compact(range.value.total) : '—',
      sub: data.value ? `完成率 ${done == null ? '—' : `${done}%`}${t?.tasks_active ? ` · ${t.tasks_active} 个进行中` : ''}` : '',
      to: { name: 'admin-tasks' },
    },
    {
      key: 'llm', label: '模型调用', icon: Activity, tone: 'lilac',
      value: l ? compact(l.requests) : '—',
      sub: successRate.value == null ? '' : `成功率 ${(successRate.value * 100).toFixed(1)}%${l?.failed_runs ? ` · ${l.failed_runs} 次失败` : ''}`,
      to: { name: 'admin-runs' },
    },
    {
      key: 'tokens', label: 'Token', icon: Hash, tone: 'sky',
      value: l ? compact(l.input_tokens + l.output_tokens) : '—',
      sub: l ? `输入 ${compact(l.input_tokens)} · 输出 ${compact(l.output_tokens)}` : '',
      to: null,
    },
    {
      key: 'cost', label: '费用', icon: Coins, tone: 'butter',
      value: costText.value,
      sub: l?.unknown_cost_runs ? `${l.unknown_cost_runs} 次待核算（模型未配置单价）` : '已全部核算',
      to: null,
    },
    {
      key: 'sources', label: '已读网页', icon: FileText, tone: 'mint',
      value: t ? compact(t.sources_read) : '—',
      sub: t ? `生成文件 ${compact(t.artifacts)} 个` : '',
      to: null,
    },
    {
      key: 'users', label: '用户', icon: Users, tone: 'lilac',
      value: t ? compact(t.users) : '—',
      sub: t ? `对话 ${compact(t.conversations)} 个` : '',
      to: { name: 'admin-users' },
    },
  ] as const
})
function openFailure(f: AdminOverview['recent_failures'][number]) {
  if (f.kind === 'task') taskOpen.value = f.id
  else void router.push({ name: 'admin-runs', query: { status: 'failed' } })
}

// ---------------------------------------------------------------- 图表配置
const PAL = {
  light: { mint: '#2bb27a', peach: '#e46a3a', sky: '#9cc4ea', text: '#303236', muted: '#8a8c92', line: 'rgba(17,18,20,.07)' },
  dark: { mint: '#5fcf9a', peach: '#f19a7c', sky: '#3f6687', text: '#dcdcd6', muted: '#8a8a85', line: 'rgba(255,255,255,.07)' },
}
const tasksOption = computed(() => {
  const rows = data.value?.tasks_by_day ?? []
  return (dark: boolean) => {
    const p = dark ? PAL.dark : PAL.light
    const bar = (name: string, color: string, values: number[], top = false) => ({
      name,
      type: 'bar',
      stack: 't',
      barMaxWidth: 22,
      data: values,
      itemStyle: { color, borderRadius: top ? [4, 4, 0, 0] : 0 },
      emphasis: { focus: 'series' },
    })
    return {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'inherit', color: p.text },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { right: 0, top: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: p.muted } },
      grid: { left: 8, right: 8, top: 36, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        data: rows.map((r) => r.date.slice(5)),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: p.muted },
      },
      yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: p.line } }, axisLabel: { color: p.muted } },
      series: [
        bar('完成', p.mint, rows.map((r) => r.completed)),
        bar('失败', p.peach, rows.map((r) => r.failed)),
        bar('其他', p.sky, rows.map((r) => Math.max(0, r.total - r.completed - r.failed)), true),
      ],
    }
  }
})
const roleOption = computed(() => {
  const rows = [...(data.value?.llm_by_role ?? [])].sort((a, b) => a.requests - b.requests)
  return (dark: boolean) => {
    const p = dark ? PAL.dark : PAL.light
    return {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'inherit', color: p.text },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (ps: { dataIndex: number }[]) => {
          const r = rows[ps[0].dataIndex]
          return `${r.label}<br/>调用 ${r.requests} 次${r.failed ? `（失败 ${r.failed}）` : ''}<br/>Token ${compact(r.input_tokens)} / ${compact(r.output_tokens)}${r.avg_ms ? `<br/>平均 ${(r.avg_ms / 1000).toFixed(1)} s` : ''}`
        },
      },
      grid: { left: 4, right: 28, top: 4, bottom: 4, containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: p.line } }, axisLabel: { color: p.muted } },
      yAxis: {
        type: 'category',
        data: rows.map((r) => r.label),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: p.text },
      },
      series: [
        {
          type: 'bar',
          data: rows.map((r) => r.requests),
          barMaxWidth: 12,
          itemStyle: { color: dark ? '#a596ef' : '#7b68d8', borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', color: p.muted, fontSize: 11 },
        },
      ],
    }
  }
})

const modelColumns: Column[] = [
  { key: 'model_name', title: '模型', minWidth: 180 },
  { key: 'requests', title: '调用', width: 80, align: 'right', sortable: true },
  { key: 'tokens', title: 'Token（入/出）', width: 150, align: 'right' },
]
const modelRows = computed(() => [...(data.value?.llm_by_model ?? [])].sort((a, b) => b.requests - a.requests))
const cooling = (e: AdminOverview['engines'][number]) => !!e.cooldown_until && new Date(e.cooldown_until).getTime() > Date.now()
</script>

<template>
  <AdminPage>
    <template #actions>
      <SegmentedControl
        v-model="days"
        small
        label="统计范围"
        :options="[
          { value: 7, label: '7 天' },
          { value: 14, label: '14 天' },
          { value: 30, label: '30 天' },
        ]"
      />
      <button class="icon-btn" :disabled="loading" aria-label="刷新" title="刷新" @click="load">
        <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
      </button>
    </template>

    <!-- KPI -->
    <div class="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
      <component
        :is="k.to ? RouterLink : 'div'"
        v-for="k in kpis"
        :key="k.key"
        :to="k.to ?? undefined"
        class="kpi ac-panel flex flex-col px-4 py-3.5"
        :class="k.to ? 'kpi-link' : ''"
      >
        <div class="flex items-center gap-2">
          <span class="flex h-6 w-6 items-center justify-center rounded-md" :style="{ background: `var(--pastel-${k.tone})`, color: `var(--pastel-${k.tone}-ink)` }">
            <component :is="k.icon" class="h-3.5 w-3.5" />
          </span>
          <span class="text-[12px] font-medium text-slate-400">{{ k.label }}</span>
          <ArrowRight v-if="k.to" class="kpi-arrow ml-auto h-3.5 w-3.5 text-slate-400" />
        </div>
        <div class="mt-2.5 truncate text-[28px] leading-8 font-bold tracking-tight text-white tabular-nums">{{ k.value }}</div>
        <div class="mt-1 truncate text-[12px] text-slate-400" :title="k.sub">{{ k.sub || '\u00a0' }}</div>
        <div v-if="k.key === 'tasks' && data" class="mt-2.5 flex h-6 items-end gap-[2px]" aria-hidden="true">
          <span
            v-for="d in data.tasks_by_day"
            :key="d.date"
            class="min-w-0 flex-1 rounded-[2px]"
            :style="{ height: `${Math.max(8, (d.total / dayMax) * 100)}%`, background: d.failed ? 'var(--pastel-peach-dot)' : 'color-mix(in srgb, var(--pastel-peach-dot) 45%, transparent)' }"
            :title="`${d.date}：${d.total} 个（失败 ${d.failed}）`"
          />
        </div>
      </component>
    </div>

    <!-- 图表 -->
    <div class="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-3">
      <section class="ac-panel xl:col-span-2">
        <div class="ac-panel-head">
          <span class="ac-panel-title">每日任务</span>
          <span class="ac-panel-sub">按创建日期，堆叠显示完成 / 失败 / 其他（进行中、已停止、草稿等）</span>
        </div>
        <div class="px-3 pt-2 pb-3">
          <AdminChart v-if="data" :option="tasksOption" :height="280" label="每日任务数量柱状图" />
          <div v-else class="h-[280px]" />
        </div>
      </section>
      <section class="ac-panel">
        <div class="ac-panel-head">
          <span class="ac-panel-title">各智能体调用次数</span>
          <span class="ac-panel-sub">悬停看 token 与平均耗时</span>
        </div>
        <div class="px-3 pt-2 pb-3">
          <AdminChart v-if="data && data.llm_by_role.length" :option="roleOption" :height="280" label="各智能体调用次数条形图" />
          <div v-else class="flex h-[280px] items-center justify-center text-[13px] text-slate-400">{{ data ? '暂无调用' : '' }}</div>
        </div>
      </section>
    </div>

    <!-- 列表 -->
    <div class="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-3">
      <section class="ac-panel overflow-hidden">
        <div class="ac-panel-head">
          <span class="ac-panel-title">按模型</span>
          <span class="flex-1" />
          <RouterLink :to="{ name: 'admin-models' }" class="text-[12px] font-medium text-slate-400 hover:text-white">管理模型 →</RouterLink>
        </div>
        <DataTable :columns="modelColumns" :rows="modelRows" :row-key="(r) => `${r.provider_name}/${r.model_name}`" :loading="loading && !data" density="compact" bare empty-text="暂无调用">
          <template #cell-model_name="{ row }">
            <div class="leading-tight">
              <div class="truncate font-medium text-white">{{ row.model_name || '—' }}</div>
              <div class="text-[11px] text-slate-500">{{ row.provider_name }}</div>
            </div>
          </template>
          <template #cell-requests="{ row }"><span class="tabular-nums">{{ compact(row.requests) }}</span></template>
          <template #cell-tokens="{ row }">
            <span class="tabular-nums">{{ compact(row.input_tokens) }} / {{ compact(row.output_tokens) }}</span>
          </template>
        </DataTable>
      </section>

      <section class="ac-panel">
        <div class="ac-panel-head">
          <span class="ac-panel-title">搜索引擎</span>
          <span class="flex-1" />
          <RouterLink :to="{ name: 'admin-diagnose' }" class="text-[12px] font-medium text-slate-400 hover:text-white">检测</RouterLink>
          <RouterLink :to="{ name: 'admin-settings', hash: '#search' }" class="text-[12px] font-medium text-slate-400 hover:text-white">配置 →</RouterLink>
        </div>
        <ul class="px-2 py-1.5">
          <li v-for="e in data?.engines ?? []" :key="e.name" class="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
            <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="!e.enabled ? 'bg-slate-500/50' : cooling(e) ? 'bg-[var(--pastel-butter-dot)]' : 'bg-[var(--pastel-mint-dot)]'" />
            <span class="min-w-0 flex-1 truncate text-[13px]" :class="e.enabled ? 'text-white' : 'text-slate-500'">{{ e.label }}</span>
            <span v-if="e.kind === 'vertical'" class="text-[11px] text-slate-500">垂直</span>
            <StatusPill v-if="cooling(e)" tone="butter" text="冷却中" :title="`冷却到 ${new Date(e.cooldown_until!).toLocaleTimeString('zh-CN')}`" />
            <span v-else-if="!e.enabled" class="text-[11px] text-slate-500">未启用</span>
          </li>
        </ul>
        <p class="border-t border-[var(--cs-line)] px-4 py-2.5 text-[11px] leading-4 text-slate-500">被拦截或网络不通的引擎会暂时冷却；冷却状态是当前服务进程内的记录。</p>
      </section>

      <section class="ac-panel">
        <div class="ac-panel-head">
          <span class="ac-panel-title">最近失败</span>
          <span class="flex-1" />
          <RouterLink :to="{ name: 'admin-tasks', query: { status: 'failed' } }" class="text-[12px] font-medium text-slate-400 hover:text-white">全部 →</RouterLink>
        </div>
        <ul v-if="data?.recent_failures.length" class="px-2 py-1.5">
          <li v-for="f in data.recent_failures" :key="`${f.kind}-${f.id}`">
            <button type="button" class="block w-full rounded-lg px-2 py-2 text-left transition hover:bg-[var(--cs-line)]" @click="openFailure(f)">
              <div class="flex items-center gap-2">
                <span class="kind">{{ f.kind === 'task' ? '任务' : '调用' }}</span>
                <span class="min-w-0 flex-1 truncate text-[13px] font-medium text-white">{{ f.title }}</span>
                <span class="shrink-0 text-[11px] text-slate-500">{{ relativeTime(f.time) }}</span>
              </div>
              <div v-if="f.detail" class="mt-0.5 line-clamp-1 pl-[42px] text-[12px] text-slate-400" :title="f.detail">{{ f.detail }}</div>
            </button>
          </li>
        </ul>
        <div v-else class="px-4 py-10 text-center text-[13px] text-slate-400">{{ data ? '这段时间没有失败' : '加载中…' }}</div>
      </section>
    </div>

    <TaskDrawer :task-id="taskOpen" @close="taskOpen = null" />
  </AdminPage>
</template>

<style scoped>
.kpi-link {
  transition: border-color 0.15s ease;
}
.kpi-link:hover {
  border-color: var(--cs-line-strong);
}
.kpi-arrow {
  opacity: 0;
  transition: opacity 0.15s ease;
}
.kpi-link:hover .kpi-arrow {
  opacity: 1;
}
.kind {
  display: inline-flex;
  flex-shrink: 0;
  border: 1px solid var(--cs-line-strong);
  border-radius: 6px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 18px;
  color: var(--color-slate-300);
}
</style>
