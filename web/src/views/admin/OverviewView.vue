<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertTriangle, Bot, Coins, FileStack, FileText, MessagesSquare, RefreshCw, Snowflake, Users } from 'lucide-vue-next'
import type { AdminOverview } from '@/api/types'
import { api } from '@/api/client'
import AdminChart from '@/components/admin/AdminChart.vue'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
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
const pct = (n: number) => (range.value.total ? `${Math.round((n / range.value.total) * 100)}%` : '—')
const llm = computed(() => data.value?.llm)
const successRate = computed(() => {
  const l = llm.value
  if (!l || !l.requests) return null
  return Math.max(0, 1 - l.failed_runs / l.requests)
})
const RING = 2 * Math.PI * 42

const smallStats = computed(() => {
  const t = data.value?.totals
  return [
    { label: '用户', value: t?.users, icon: Users, tone: 'lilac' },
    { label: '对话', value: t?.conversations, icon: MessagesSquare, tone: 'sky' },
    { label: '成果文件', value: t?.artifacts, icon: FileStack, tone: 'butter' },
    { label: '已读网页', value: t?.sources_read, icon: FileText, tone: 'mint' },
  ] as const
})

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
      barMaxWidth: 26,
      data: values,
      itemStyle: { color, borderRadius: top ? [8, 8, 0, 0] : 0 },
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
          barMaxWidth: 14,
          itemStyle: { color: dark ? '#a596ef' : '#7b68d8', borderRadius: [0, 7, 7, 0] },
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
        label="统计范围"
        :options="[
          { value: 7, label: '7 天' },
          { value: 14, label: '14 天' },
          { value: 30, label: '30 天' },
        ]"
      />
      <button class="round-btn-light" :disabled="loading" aria-label="刷新" title="刷新" @click="load">
        <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
      </button>
    </template>

    <div class="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-12 [&>*]:min-w-0">
      <!-- 主卡片：任务 -->
      <section class="hero flex flex-col p-6 xl:col-span-4" aria-label="任务概况">
        <div class="flex items-center justify-between text-sm font-semibold opacity-90">
          <span>近 {{ days }} 天任务</span>
          <span v-if="data?.totals.tasks_active" class="rounded-full bg-white/20 px-2.5 py-0.5 text-xs">{{ data.totals.tasks_active }} 个进行中</span>
        </div>
        <div class="mt-3 text-[56px] leading-none font-bold tracking-tight tabular-nums">{{ data ? compact(range.total) : '—' }}</div>
        <div class="mt-1 text-sm opacity-80">累计 {{ data ? compact(data.totals.tasks) : '—' }} 个任务</div>
        <div v-if="data" class="mt-5 flex h-14 items-end gap-[3px]" aria-hidden="true">
          <span
            v-for="d in data.tasks_by_day"
            :key="d.date"
            class="min-w-0 flex-1 rounded-t-[4px] bg-white/35"
            :style="{ height: `${Math.max(6, (d.total / dayMax) * 100)}%` }"
            :title="`${d.date}：${d.total} 个`"
          />
        </div>
        <div class="mt-auto grid grid-cols-3 pt-6">
          <div class="pr-3">
            <div class="text-xs opacity-75">完成</div>
            <div class="mt-0.5 text-xl font-bold tabular-nums">{{ pct(range.completed) }}</div>
          </div>
          <div class="hero-split px-3">
            <div class="text-xs opacity-75">失败</div>
            <div class="mt-0.5 text-xl font-bold tabular-nums">{{ pct(range.failed) }}</div>
          </div>
          <div class="hero-split pl-3">
            <div class="text-xs opacity-75">其他</div>
            <div class="mt-0.5 text-xl font-bold tabular-nums">{{ pct(range.total - range.completed - range.failed) }}</div>
          </div>
        </div>
      </section>

      <!-- 模型调用 -->
      <section class="surface flex flex-col p-6 xl:col-span-4" aria-label="模型调用">
        <div class="flex items-center justify-between">
          <h2 class="card-title"><Bot class="h-4.5 w-4.5" /> 模型调用</h2>
          <RouterLink :to="{ name: 'admin-runs' }" class="text-xs font-semibold text-slate-400 hover:text-white">调用记录 →</RouterLink>
        </div>
        <div class="mt-2 flex items-center gap-6">
          <div class="min-w-0 flex-1">
            <div class="text-[44px] leading-none font-bold tracking-tight text-white tabular-nums">{{ llm ? compact(llm.requests) : '—' }}</div>
            <div class="mt-1 text-sm text-slate-400">次请求（{{ days }} 天）</div>
            <dl class="mt-4 space-y-1.5 text-sm">
              <div class="flex items-center gap-2">
                <span class="h-2 w-2 rounded-full bg-[var(--pastel-sky-dot)]" />
                <dt class="text-slate-400">输入 token</dt>
                <dd class="ml-auto font-semibold tabular-nums">{{ llm ? compact(llm.input_tokens) : '—' }}</dd>
              </div>
              <div class="flex items-center gap-2">
                <span class="h-2 w-2 rounded-full bg-[var(--pastel-lilac-dot)]" />
                <dt class="text-slate-400">输出 token</dt>
                <dd class="ml-auto font-semibold tabular-nums">{{ llm ? compact(llm.output_tokens) : '—' }}</dd>
              </div>
            </dl>
          </div>
          <div class="relative h-[110px] w-[110px] shrink-0" :title="successRate == null ? '' : `成功率 ${(successRate * 100).toFixed(1)}%`">
            <svg viewBox="0 0 100 100" class="h-full w-full -rotate-90" aria-hidden="true">
              <circle cx="50" cy="50" r="42" fill="none" stroke="var(--cs-line-strong)" stroke-width="9" />
              <circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke="var(--pastel-mint-dot)"
                stroke-width="9"
                stroke-linecap="round"
                :stroke-dasharray="RING"
                :stroke-dashoffset="RING * (1 - (successRate ?? 0))"
                style="transition: stroke-dashoffset 0.6s ease"
              />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span class="text-lg font-bold text-white tabular-nums">{{ successRate == null ? '—' : `${Math.round(successRate * 100)}%` }}</span>
              <span class="text-[11px] text-slate-400">成功率</span>
            </div>
          </div>
        </div>
        <div class="hairline mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-4 text-sm">
          <Coins class="h-4 w-4 text-slate-400" />
          <span class="text-slate-400">费用</span>
          <span v-if="!llm?.cost.length" class="font-semibold">—</span>
          <span v-for="c in llm?.cost ?? []" :key="c.currency_code" class="font-semibold tabular-nums">{{ money(c.minor_amt, c.currency_code) }}</span>
          <span v-if="llm?.unknown_cost_runs" class="pill card-butter accent-ink" title="这些调用的模型没有配置单价，未计入费用">{{ llm.unknown_cost_runs }} 次待核算</span>
          <span v-if="llm?.failed_runs" class="ml-auto text-xs text-rose-300">{{ llm.failed_runs }} 次失败</span>
        </div>
      </section>

      <!-- 小统计 -->
      <div class="grid grid-cols-2 gap-4 xl:col-span-4">
        <div v-for="s in smallStats" :key="s.label" class="surface flex flex-col p-5">
          <span class="flex h-10 w-10 items-center justify-center rounded-2xl" :class="`card-${s.tone}`">
            <component :is="s.icon" class="h-5 w-5 accent-ink" />
          </span>
          <span class="mt-auto pt-4 text-[30px] leading-9 font-bold tracking-tight text-white tabular-nums">{{ s.value == null ? '—' : compact(s.value) }}</span>
          <span class="text-sm text-slate-400">{{ s.label }}</span>
        </div>
      </div>

      <!-- 每日任务 -->
      <section class="surface p-6 xl:col-span-8">
        <h2 class="card-title">每日任务</h2>
        <p class="text-xs text-slate-400">按创建日期统计，堆叠显示完成 / 失败 / 其他（进行中、已停止、草稿等）</p>
        <AdminChart v-if="data" class="mt-3" :option="tasksOption" :height="300" label="每日任务数量柱状图" />
      </section>

      <!-- 智能体调用 -->
      <section class="surface p-6 xl:col-span-4">
        <h2 class="card-title">各智能体调用次数</h2>
        <p class="text-xs text-slate-400">悬停查看 token 与平均耗时</p>
        <AdminChart v-if="data && data.llm_by_role.length" class="mt-3" :option="roleOption" :height="300" label="各智能体调用次数条形图" />
        <div v-else-if="data" class="flex h-[300px] items-center justify-center text-sm text-slate-400">暂无调用</div>
      </section>

      <!-- 按模型 -->
      <section class="xl:col-span-5">
        <h2 class="card-title mb-3 px-1">按模型</h2>
        <DataTable :columns="modelColumns" :rows="modelRows" :row-key="(r) => `${r.provider_name}/${r.model_name}`" :loading="loading && !data" density="compact" empty-text="暂无调用">
          <template #cell-model_name="{ row }">
            <div class="leading-tight">
              <div class="truncate font-semibold text-white">{{ row.model_name || '—' }}</div>
              <div class="text-[11px] text-slate-500">{{ row.provider_name }}</div>
            </div>
          </template>
          <template #cell-requests="{ row }"><span class="tabular-nums">{{ compact(row.requests) }}</span></template>
          <template #cell-tokens="{ row }">
            <span class="tabular-nums">{{ compact(row.input_tokens) }} / {{ compact(row.output_tokens) }}</span>
          </template>
        </DataTable>
      </section>

      <!-- 搜索引擎 -->
      <section class="surface p-5 xl:col-span-3">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="card-title">搜索引擎</h2>
          <RouterLink :to="{ name: 'admin-search' }" class="text-xs font-semibold text-slate-400 hover:text-white">配置 →</RouterLink>
        </div>
        <ul class="space-y-1">
          <li v-for="e in data?.engines ?? []" :key="e.name" class="flex items-center gap-2.5 rounded-xl px-2 py-1.5">
            <span class="h-2 w-2 shrink-0 rounded-full" :class="!e.enabled ? 'bg-slate-500/50' : cooling(e) ? 'bg-[var(--pastel-butter-dot)]' : 'bg-[var(--pastel-mint-dot)]'" />
            <span class="min-w-0 flex-1 truncate text-sm" :class="e.enabled ? 'text-white' : 'text-slate-500'">{{ e.label }}</span>
            <span v-if="e.kind === 'vertical'" class="text-[11px] text-slate-500">垂直</span>
            <StatusPill v-if="cooling(e)" tone="butter" text="冷却中" :title="`冷却到 ${new Date(e.cooldown_until!).toLocaleTimeString('zh-CN')}`" />
            <span v-else-if="!e.enabled" class="text-[11px] text-slate-500">未启用</span>
          </li>
        </ul>
        <p class="mt-3 flex items-start gap-1.5 text-[11px] leading-4 text-slate-500">
          <Snowflake class="mt-px h-3 w-3 shrink-0" /> 被拦截或网络不通的引擎会暂时冷却，冷却状态为当前服务进程内的记录。
        </p>
      </section>

      <!-- 最近失败 -->
      <section class="surface p-5 xl:col-span-4">
        <h2 class="card-title mb-3"><AlertTriangle class="h-4.5 w-4.5 text-rose-300" /> 最近失败</h2>
        <ul v-if="data?.recent_failures.length" class="space-y-1">
          <li v-for="f in data.recent_failures" :key="`${f.kind}-${f.id}`">
            <component
              :is="f.conversation_id ? RouterLink : 'div'"
              :to="f.conversation_id ? { name: 'chat', params: { id: f.conversation_id } } : undefined"
              class="block rounded-xl px-2.5 py-2 transition hover:bg-[var(--cs-line)]"
            >
              <div class="flex items-center gap-2">
                <span class="pill !py-0 text-[11px]" :class="f.kind === 'task' ? 'card-peach accent-ink' : 'card-lilac accent-ink'">{{ f.kind === 'task' ? '任务' : '调用' }}</span>
                <span class="min-w-0 flex-1 truncate text-sm font-semibold text-white">{{ f.title }}</span>
                <span class="shrink-0 text-[11px] text-slate-500">{{ relativeTime(f.time) }}</span>
              </div>
              <div v-if="f.detail" class="mt-0.5 line-clamp-1 pl-1 text-xs text-slate-400" :title="f.detail">{{ f.detail }}</div>
            </component>
          </li>
        </ul>
        <div v-else class="flex flex-col items-center py-8 text-center">
          <span class="text-2xl" aria-hidden="true">🌿</span>
          <span class="mt-1 text-sm text-slate-400">{{ data ? '这段时间没有失败' : '加载中…' }}</span>
        </div>
      </section>
    </div>
  </AdminPage>
</template>

<style scoped>
.hero {
  border-radius: 28px;
  background: #e8673a;
  color: #fff;
  min-height: 260px;
  box-shadow: 0 18px 40px -22px rgb(232 103 58 / 0.7);
}
html.dark .hero {
  background: #c4552d;
  box-shadow: none;
}
.hero-split {
  border-left: 2px dotted rgb(255 255 255 / 0.45);
}
</style>
