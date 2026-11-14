<script setup lang="ts">
import { computed, ref } from 'vue'
import { FileCog, Globe, Loader2, Play, Radar, ShieldCheck, Square } from 'lucide-vue-next'
import type { DiagnoseResult, DiagnoseStatus } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import SaveBar from '@/components/admin/SaveBar.vue'
import SettingFieldControl from '@/components/admin/SettingFieldControl.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import type { Pastel } from '@/lib/adminFormat'
import { useAdminSettings } from '@/lib/useAdminSettings'

const s = useAdminSettings(['search', 'browser'])
const searchFields = computed(() => s.fields.value.filter((f) => f.group === 'search'))
const browserFields = computed(() => s.fields.value.filter((f) => f.group === 'browser'))

// ---------------------------------------------------------------- 引擎检测：逐个引擎请求，结果逐行出现
const query = ref('故宫博物院 开放时间')
const running = ref(false)
const stopRequested = ref(false)
const env = ref<{ browser: string; proxy: string | null } | null>(null)
interface Row extends DiagnoseResult {
  pending?: boolean
}
const results = ref<Row[]>([])

const engineField = computed(() => s.data.value?.fields.find((f) => f.key === 'search_engines'))
const verticalField = computed(() => s.data.value?.fields.find((f) => f.key === 'search_vertical_sources'))
const toCheck = computed(() => {
  const eng = (engineField.value?.value as string[] | null) ?? []
  const vert = (verticalField.value?.value as string[] | null) ?? (verticalField.value?.options ?? []).map((o) => o.value)
  const labels = new Map<string, string>()
  for (const f of [engineField.value, verticalField.value]) for (const o of f?.options ?? []) labels.set(o.value, o.label)
  return [...new Set([...eng, ...vert])].map((name) => ({ name, label: labels.get(name) ?? name }))
})

const STATUS: Record<DiagnoseStatus, { label: string; tone: Pastel }> = {
  ok: { label: '可用', tone: 'mint' },
  empty: { label: '无结果', tone: 'gray' },
  irrelevant: { label: '结果无关', tone: 'butter' },
  blocked: { label: '需人机验证', tone: 'lilac' },
  unreachable: { label: '无法访问', tone: 'peach' },
  error: { label: '出错', tone: 'peach' },
}

async function runDiagnose() {
  if (!query.value.trim() || running.value) return
  running.value = true
  stopRequested.value = false
  results.value = toCheck.value.map((e) => ({ ...e, status: 'empty', count: 0, seconds: 0, sample: null, detail: null, pending: true }))
  for (const [i, e] of toCheck.value.entries()) {
    if (stopRequested.value) break
    try {
      const out = await api.diagnoseSearch(query.value.trim(), [e.name])
      env.value = { browser: out.browser, proxy: out.proxy }
      const r = out.results[0]
      results.value[i] = r ? { ...r } : { ...results.value[i], status: 'error', detail: '服务端没有返回结果', pending: false }
    } catch (err) {
      results.value[i] = { ...results.value[i], status: 'error', detail: err instanceof Error ? err.message : '检测失败', pending: false }
    }
  }
  results.value = results.value.filter((r) => !r.pending)
  running.value = false
}
const okCount = computed(() => results.value.filter((r) => r.status === 'ok').length)

const columns: Column[] = [
  { key: 'label', title: '引擎 / 来源', width: 160 },
  { key: 'status', title: '结果', width: 120 },
  { key: 'count', title: '条数', width: 64, align: 'right' },
  { key: 'seconds', title: '耗时', width: 72, align: 'right' },
  { key: 'detail', title: '说明', minWidth: 200 },
]
</script>

<template>
  <AdminPage>
    <div v-if="s.loading.value && !s.data.value" class="flex items-center gap-2 text-sm text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> 加载中…</div>
    <div v-else class="grid grid-cols-[minmax(0,1fr)] items-start gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div class="space-y-5">
        <section class="surface p-5 lg:p-6">
          <h2 class="card-title mb-1"><Globe class="h-4.5 w-4.5" /> 搜索</h2>
          <p class="mb-4 text-sm text-slate-400">任务按顺序使用可用的引擎；被拦截或网络不通的引擎会自动冷却并跳过。</p>
          <div class="space-y-3">
            <SettingFieldControl
              v-for="f in searchFields"
              :key="f.key"
              v-model="s.drafts[f.key]"
              :field="f"
              :dirty="s.dirtyKeys.value.includes(f.key)"
              @reset="s.reset(f.key)"
            />
          </div>
        </section>
        <section class="surface p-5 lg:p-6">
          <h2 class="card-title mb-1"><ShieldCheck class="h-4.5 w-4.5" /> 浏览器与人工接手</h2>
          <p class="mb-4 text-sm text-slate-400">遇到人机验证时暂停任务，请用户在实时画面中完成验证；系统不会尝试绕过验证。</p>
          <div class="space-y-3">
            <SettingFieldControl
              v-for="f in browserFields"
              :key="f.key"
              v-model="s.drafts[f.key]"
              :field="f"
              :dirty="s.dirtyKeys.value.includes(f.key)"
              @reset="s.reset(f.key)"
            />
          </div>
        </section>
      </div>

      <div class="space-y-5 xl:sticky xl:top-6">
        <section class="card-mint p-5 lg:p-6">
          <h2 class="card-title accent-ink"><Radar class="h-4.5 w-4.5" /> 引擎检测</h2>
          <p class="mt-1 text-sm accent-ink opacity-80">
            用服务器上的浏览器真实打开每个引擎搜索一次，判断在当前网络与代理下哪些可用。每个引擎最长约 1 分钟。
          </p>
          <form class="mt-4 flex flex-wrap gap-2" @submit.prevent="runDiagnose">
            <input v-model="query" class="input min-w-0 flex-1 !rounded-full" placeholder="测试查询词" aria-label="测试查询词" :disabled="running" />
            <button v-if="!running" type="submit" class="btn-primary" :disabled="!toCheck.length"><Play class="h-4 w-4" /> 开始检测</button>
            <button v-else type="button" class="btn-secondary" @click="stopRequested = true">
              <Square class="h-3.5 w-3.5" /> {{ stopRequested ? '本项完成后停止' : '停止' }}
            </button>
          </form>
          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs accent-ink opacity-80">
            <span>将检测 {{ toCheck.length }} 个：{{ toCheck.map((e) => e.label).join('、') }}</span>
            <template v-if="env">
              <span>浏览器：{{ env.browser }}</span>
              <span>代理：{{ env.proxy || '未设置（直连）' }}</span>
            </template>
          </div>
        </section>

        <DataTable
          v-if="results.length"
          :columns="columns"
          :rows="results"
          row-key="name"
          density="compact"
        >
          <template #cell-label="{ row }">
            <div class="leading-tight">
              <div class="font-semibold text-white">{{ row.label }}</div>
              <div class="font-mono text-[11px] text-slate-500">{{ row.name }}</div>
            </div>
          </template>
          <template #cell-status="{ row }">
            <span v-if="row.pending" class="inline-flex items-center gap-1.5 text-xs text-slate-400">
              <Loader2 v-if="running" class="h-3.5 w-3.5 animate-spin" /> {{ running ? '等待检测' : '未检测' }}
            </span>
            <StatusPill v-else :tone="STATUS[row.status].tone" :text="STATUS[row.status].label" />
          </template>
          <template #cell-count="{ row }"><span class="tabular-nums">{{ row.pending ? '' : row.count }}</span></template>
          <template #cell-seconds="{ row }"><span class="tabular-nums">{{ row.pending ? '' : `${row.seconds.toFixed(1)}s` }}</span></template>
          <template #cell-detail="{ row }">
            <span class="line-clamp-2 text-xs text-slate-400" :title="row.detail ?? row.sample ?? ''">
              {{ row.status === 'ok' && row.sample ? `例：${row.sample}` : (row.detail ?? '') }}
            </span>
          </template>
        </DataTable>
        <p v-if="results.length && !running" class="-mt-2 px-1 text-sm text-slate-400">
          可用 {{ okCount }}/{{ results.length }}。<template v-if="okCount < results.length">不可用的引擎可在左侧停用或调后；“无法访问”通常需要在 config.yaml 设置 browser.proxy。</template>
        </p>

        <section v-if="s.data.value?.static.length" class="surface p-5 lg:p-6">
          <h2 class="card-title"><FileCog class="h-4.5 w-4.5" /> 部署配置（只读）</h2>
          <p class="mt-1 text-sm text-slate-400">
            以下项在 config.yaml 中修改，重启后生效：<code class="rounded bg-[var(--cs-code-bg)] px-1.5 py-0.5 font-mono text-xs">{{ s.data.value.config_path }}</code>
          </p>
          <div class="mt-4 grid gap-4 sm:grid-cols-2">
            <div v-for="g in s.data.value.static" :key="g.group" class="rounded-2xl sunken p-4">
              <div class="mb-2 text-xs font-bold tracking-wide text-slate-400">{{ g.group }}</div>
              <dl class="space-y-1.5 text-sm">
                <div v-for="it in g.items" :key="it.label" class="flex gap-3">
                  <dt class="w-24 shrink-0 text-slate-400">{{ it.label }}</dt>
                  <dd class="min-w-0 flex-1 truncate font-mono text-xs leading-5 text-slate-200" :title="it.value">{{ it.value }}</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>
      </div>
    </div>
    <SaveBar :count="s.dirtyKeys.value.length" :saving="s.saving.value" @save="s.save()" @discard="s.discard()" />
  </AdminPage>
</template>
