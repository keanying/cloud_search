<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Lightbulb, Loader2, Play, Square } from 'lucide-vue-next'
import type { AdminSettings, DiagnoseResult, DiagnoseStatus } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import type { Pastel } from '@/lib/adminFormat'
import { useToastStore } from '@/stores/toast'

/** 引擎检测：逐个引擎请求服务端真实搜索一次，结果逐行出现；可在当前引擎完成后停止 */
const toast = useToastStore()
const settings = ref<AdminSettings | null>(null)
onMounted(async () => {
  try {
    settings.value = await api.adminSettings()
  } catch (e) {
    toast.error(e, '加载引擎列表失败')
  }
})

const query = ref('故宫博物院 开放时间')
const running = ref(false)
const stopRequested = ref(false)
const env = ref<{ browser: string; proxy: string | null } | null>(null)
interface Row extends DiagnoseResult {
  pending?: boolean
  kind: '通用' | '垂直'
}
const results = ref<Row[]>([])
const startedAt = ref<number | null>(null)

const engineField = computed(() => settings.value?.fields.find((f) => f.key === 'search_engines'))
const verticalField = computed(() => settings.value?.fields.find((f) => f.key === 'search_vertical_sources'))
const toCheck = computed(() => {
  const eng = (engineField.value?.value as string[] | null) ?? []
  const vert = (verticalField.value?.value as string[] | null) ?? (verticalField.value?.options ?? []).map((o) => o.value)
  const labels = new Map<string, string>()
  for (const f of [engineField.value, verticalField.value]) for (const o of f?.options ?? []) labels.set(o.value, o.label)
  return [
    ...eng.map((name) => ({ name, label: labels.get(name) ?? name, kind: '通用' as const })),
    ...vert.filter((v) => !eng.includes(v)).map((name) => ({ name, label: labels.get(name) ?? name, kind: '垂直' as const })),
  ]
})

const STATUS: Record<DiagnoseStatus, { label: string; tone: Pastel }> = {
  ok: { label: '可用', tone: 'mint' },
  empty: { label: '无结果', tone: 'gray' },
  irrelevant: { label: '结果无关', tone: 'butter' },
  blocked: { label: '需人机验证', tone: 'lilac' },
  unreachable: { label: '无法访问', tone: 'peach' },
  error: { label: '出错', tone: 'peach' },
}

async function run() {
  if (!query.value.trim() || running.value) return
  running.value = true
  stopRequested.value = false
  startedAt.value = Date.now()
  results.value = toCheck.value.map((e) => ({ ...e, status: 'empty', count: 0, seconds: 0, sample: null, detail: null, pending: true }))
  for (const [i, e] of toCheck.value.entries()) {
    if (stopRequested.value) break
    try {
      const out = await api.diagnoseSearch(query.value.trim(), [e.name])
      env.value = { browser: out.browser, proxy: out.proxy }
      const r = out.results[0]
      results.value[i] = r ? { ...r, kind: e.kind } : { ...results.value[i], status: 'error', detail: '服务端没有返回结果', pending: false }
    } catch (err) {
      results.value[i] = { ...results.value[i], status: 'error', detail: err instanceof Error ? err.message : '检测失败', pending: false }
    }
  }
  running.value = false
}
const done = computed(() => results.value.filter((r) => !r.pending))
const count = (st: DiagnoseStatus) => done.value.filter((r) => r.status === st).length
const hints = computed(() => {
  const out: string[] = []
  if (count('unreachable')) out.push('“无法访问”通常是网络不通或被拒绝：在 config.yaml 设置 browser.proxy（与本机能访问外网的代理一致），重启后再检测。')
  if (count('blocked')) out.push('“需人机验证”的引擎在任务中会请用户接手完成验证；频繁出现时可在「运行参数」中把它调到后面或停用。')
  if (count('irrelevant')) out.push('“结果无关”多为风控返回了无关内容；任务会自动换下一个引擎。')
  if (count('empty')) out.push('“无结果”可能是查询词在该来源下确实没有内容，可换一个更通用的查询词再试。')
  return out
})

const columns: Column[] = [
  { key: 'label', title: '引擎 / 来源', width: 220 },
  { key: 'kind', title: '类型', width: 80 },
  { key: 'status', title: '结果', width: 130 },
  { key: 'count', title: '条数', width: 72, align: 'right' },
  { key: 'seconds', title: '耗时', width: 80, align: 'right' },
  { key: 'detail', title: '说明', minWidth: 280 },
]
</script>

<template>
  <AdminPage>
    <div class="ac-panel mb-4 p-4">
      <form class="flex flex-wrap items-center gap-2" @submit.prevent="run">
        <input v-model="query" class="input min-w-0 flex-1 sm:max-w-md" placeholder="测试查询词" aria-label="测试查询词" :disabled="running" />
        <button v-if="!running" type="submit" class="btn-primary" :disabled="!toCheck.length || !query.trim()"><Play class="h-4 w-4" /> 开始检测</button>
        <button v-else type="button" class="btn-secondary" :disabled="stopRequested" @click="stopRequested = true">
          <Square class="h-3.5 w-3.5" /> {{ stopRequested ? '本项完成后停止…' : '停止' }}
        </button>
        <span class="text-[12px] text-slate-400">每个引擎最长约 1 分钟</span>
      </form>
      <div class="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-slate-400">
        <span>将检测 {{ toCheck.length }} 个（{{ toCheck.filter((e) => e.kind === '通用').length }} 个通用引擎 + {{ toCheck.filter((e) => e.kind === '垂直').length }} 个垂直来源）</span>
        <span v-if="env">浏览器：{{ env.browser }}</span>
        <span v-if="env">代理：{{ env.proxy || '未设置（直连）' }}</span>
        <RouterLink :to="{ name: 'admin-settings', hash: '#search' }" class="font-semibold text-slate-300 hover:underline">调整引擎顺序 →</RouterLink>
      </div>
    </div>

    <div v-if="done.length" class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      <div v-for="st in (['ok', 'blocked', 'unreachable', 'irrelevant', 'empty', 'error'] as DiagnoseStatus[])" :key="st" class="ac-panel px-4 py-3">
        <div class="text-[22px] leading-7 font-bold text-white tabular-nums">{{ count(st) }}</div>
        <div class="mt-0.5 flex items-center gap-1.5 text-[12px] text-slate-400">
          <span class="h-1.5 w-1.5 rounded-full" :style="{ background: STATUS[st].tone === 'gray' ? 'var(--color-slate-500)' : `var(--pastel-${STATUS[st].tone}-dot)` }" />
          {{ STATUS[st].label }}
        </div>
      </div>
    </div>

    <DataTable
      :columns="columns"
      :rows="results"
      row-key="name"
      empty-text="还没有检测结果"
      empty-desc="点「开始检测」，用服务器上的浏览器真实打开每个引擎搜索一次"
    >
      <template #cell-label="{ row }">
        <div class="leading-tight">
          <div class="font-semibold text-white">{{ row.label }}</div>
          <div class="font-mono text-[11px] text-slate-500">{{ row.name }}</div>
        </div>
      </template>
      <template #cell-kind="{ row }"><span class="text-slate-400">{{ row.kind }}</span></template>
      <template #cell-status="{ row }">
        <span v-if="row.pending" class="inline-flex items-center gap-1.5 text-[12px] text-slate-400">
          <Loader2 v-if="running" class="h-3.5 w-3.5 animate-spin" /> {{ running ? '等待检测' : '未检测' }}
        </span>
        <StatusPill v-else :tone="STATUS[row.status].tone" :text="STATUS[row.status].label" />
      </template>
      <template #cell-count="{ row }"><span class="tabular-nums">{{ row.pending ? '' : row.count }}</span></template>
      <template #cell-seconds="{ row }"><span class="tabular-nums">{{ row.pending ? '' : `${row.seconds.toFixed(1)} s` }}</span></template>
      <template #cell-detail="{ row }">
        <span class="line-clamp-2 text-[12px] text-slate-400" :title="row.detail ?? row.sample ?? ''">
          {{ row.status === 'ok' && row.sample ? `例：${row.sample}` : (row.detail ?? '') }}
        </span>
      </template>
    </DataTable>

    <div v-if="hints.length && !running" class="ac-panel mt-4 px-4 py-3">
      <div class="mb-1.5 flex items-center gap-1.5 text-[13px] font-semibold text-white"><Lightbulb class="h-4 w-4 text-slate-400" /> 怎么处理</div>
      <ul class="list-disc space-y-1 pl-5 text-[12px] leading-5 text-slate-300">
        <li v-for="h in hints" :key="h">{{ h }}</li>
      </ul>
    </div>
  </AdminPage>
</template>
