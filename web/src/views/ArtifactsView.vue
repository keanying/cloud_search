<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Download, Eye, LayoutGrid, List, Loader2, MessageSquare, X } from 'lucide-vue-next'
import type { ArtifactFormatName, ArtifactOut } from '@/api/types'
import { api } from '@/api/client'
import ArtifactPanel from '@/components/panel/ArtifactPanel.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatTiles from '@/components/task/StatTiles.vue'
import { FORMAT_LABEL, FORMAT_TONE, formatOfName } from '@/lib/artifactFormats'
import { artifactKindLabel, formatBytes, formatTime, qualityLabel, relativeTime } from '@/lib/format'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const items = ref<ArtifactOut[]>([])
const loaded = ref(false)
const filter = ref<'all' | 'data' | 'report' | 'other'>('all')
const q = ref('')
const VIEW_KEY = 'cs_artifacts_view'
const view = ref<'grid' | 'table'>((localStorage.getItem(VIEW_KEY) as 'grid' | 'table') || 'grid')
watch(view, (v) => localStorage.setItem(VIEW_KEY, v))
const preview = ref<{ id: string; name: string } | null>(null)
const busy = ref<string | null>(null)

const FILTERS = [
  { v: 'all', label: '全部', emoji: '🗂️' },
  { v: 'report', label: '报告', emoji: '📝' },
  { v: 'data', label: '数据', emoji: '📊' },
  { v: 'other', label: '其他文件', emoji: '📎' },
] as const

type Kind = 'data' | 'report' | 'other'
function kindOf(a: ArtifactOut): Kind {
  if (a.artifact_kind === 'dataset' || a.artifact_kind === 'data_dictionary') return 'data'
  if (a.artifact_kind === 'report' || a.artifact_kind === 'answer') return 'report'
  return 'other'
}

/** 同一份成果的多种格式（同任务、同名不同扩展名）合并为一项 */
interface Group {
  key: string
  name: string
  kind: Kind
  artifactKind: string
  files: (ArtifactOut & { fmt: ArtifactFormatName | null })[]
  conversationId: string | null
  createdTime: string
  recordQty: number | null
  quality: string
  available: boolean
}
const ORDER: ArtifactFormatName[] = ['docx', 'pdf', 'xlsx', 'html', 'csv', 'md', 'json']
const baseName = (n: string) => n.replace(/\.[A-Za-z0-9]{1,5}$/, '')

const groups = computed<Group[]>(() => {
  const map = new Map<string, Group>()
  for (const a of items.value) {
    const key = `${a.task_id ?? a.artifact_id}::${a.artifact_kind}::${baseName(a.display_name)}`
    let g = map.get(key)
    if (!g) {
      g = {
        key,
        name: baseName(a.display_name),
        kind: kindOf(a),
        artifactKind: a.artifact_kind,
        files: [],
        conversationId: a.conversation_id,
        createdTime: a.created_time,
        recordQty: a.record_qty,
        quality: a.quality_status,
        available: false,
      }
      map.set(key, g)
    }
    g.files.push({ ...a, fmt: formatOfName(a.display_name) })
    if (a.created_time > g.createdTime) g.createdTime = a.created_time
    if (a.record_qty != null) g.recordQty = a.record_qty
    g.available ||= a.artifact_status === 'available'
  }
  const out = [...map.values()]
  for (const g of out) g.files.sort((x, y) => idx(x.fmt) - idx(y.fmt))
  return out.sort((a, b) => (a.createdTime < b.createdTime ? 1 : -1))
})
function idx(f: ArtifactFormatName | null) {
  const i = f ? ORDER.indexOf(f) : -1
  return i < 0 ? 99 : i
}

const counts = computed(() => ({
  report: groups.value.filter((g) => g.kind === 'report').length,
  data: groups.value.filter((g) => g.kind === 'data').length,
}))
const shown = computed(() => {
  const k = q.value.toLowerCase()
  return groups.value.filter((g) => (filter.value === 'all' || g.kind === filter.value) && (!k || g.name.toLowerCase().includes(k)))
})

const toneOf = (g: Group) => (g.kind === 'data' ? 'mint' : g.kind === 'report' ? 'lilac' : 'sky')
const totalBytes = (g: Group) => g.files.reduce((a, f) => a + f.byte_qty, 0)
/** 预览优先 HTML（与下载排版一致），其次表格/PDF/首个文件 */
function previewFile(g: Group) {
  for (const f of ['html', 'xlsx', 'csv', 'md', 'pdf'] as const) {
    const hit = g.files.find((x) => x.fmt === f)
    if (hit) return hit
  }
  return g.files[0]
}
const fmtLabel = (f: ArtifactOut & { fmt: ArtifactFormatName | null }) =>
  f.fmt ? FORMAT_LABEL[f.fmt] : (f.display_name.match(/\.([A-Za-z0-9]{1,5})$/)?.[1] ?? '文件').toUpperCase()
const dotOf = (f: { fmt: ArtifactFormatName | null }) => `var(--pastel-${f.fmt ? FORMAT_TONE[f.fmt] : 'sky'}-dot)`

onMounted(async () => {
  try {
    items.value = await api.listArtifacts()
  } catch (e) {
    toast.error(e)
  } finally {
    loaded.value = true
  }
})

async function download(a: ArtifactOut) {
  busy.value = a.artifact_id
  try {
    await api.downloadArtifact(a.artifact_id, a.display_name)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    busy.value = null
  }
}
function openPreview(g: Group) {
  const f = previewFile(g)
  preview.value = { id: f.artifact_id, name: g.name }
}

const columns: Column[] = [
  { key: 'name', title: '名称', minWidth: 320 },
  { key: 'kind', title: '类型', width: 90 },
  { key: 'formats', title: '格式（点击下载）', minWidth: 300 },
  { key: 'size', title: '大小', width: 100, align: 'right' },
  { key: 'createdTime', title: '生成时间', width: 170, sortable: true },
  { key: 'actions', title: '', width: 130, align: 'right' },
]
</script>

<template>
  <div class="flex h-full gap-3 p-3">
    <div class="min-w-0 flex-1 overflow-y-auto">
      <div class="mx-auto w-full max-w-[1680px] px-4 pt-3 pb-12 md:px-6 xl:px-10">
        <PageHeader title="我的成果" desc="对话中生成的报告与数据文件。同一份成果的 Word / PDF / Excel 等格式合并显示。" :parent="{ name: 'home' }">
          <StatTiles
            class="w-full sm:w-[420px]"
            :items="[
              { label: '报告', value: counts.report, tone: 'lilac' },
              { label: '数据', value: counts.data, tone: 'mint' },
              { label: '全部成果', value: groups.length, tone: 'butter' },
            ]"
          />
        </PageHeader>

        <FilterBar v-model:q="q" placeholder="搜索成果名称">
          <div class="flex flex-wrap gap-2" role="tablist" aria-label="筛选成果">
            <button
              v-for="f in FILTERS"
              :key="f.v"
              role="tab"
              :aria-selected="filter === f.v"
              class="chip"
              :class="filter === f.v ? 'chip-active' : ''"
              @click="filter = f.v"
            >
              {{ f.emoji }} {{ f.label }}
            </button>
          </div>
          <template #actions>
            <div class="sunken hairline inline-flex gap-0.5 rounded-full border p-1" role="radiogroup" aria-label="显示方式">
              <button
                type="button"
                role="radio"
                :aria-checked="view === 'grid'"
                class="rounded-full p-1.5"
                :class="view === 'grid' ? 'chip-active' : 'text-slate-400'"
                title="卡片"
                @click="view = 'grid'"
              >
                <LayoutGrid class="h-4 w-4" />
              </button>
              <button
                type="button"
                role="radio"
                :aria-checked="view === 'table'"
                class="rounded-full p-1.5"
                :class="view === 'table' ? 'chip-active' : 'text-slate-400'"
                title="列表"
                @click="view = 'table'"
              >
                <List class="h-4 w-4" />
              </button>
            </div>
          </template>
        </FilterBar>

        <div v-if="loaded && !groups.length" class="surface flex flex-col items-center px-6 py-14 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-full card-sky text-2xl" aria-hidden="true">📂</span>
          <h2 class="mt-4 text-lg font-bold text-white">你的数据和报告会出现在这里</h2>
          <p class="mt-1 text-sm text-slate-400">在对话中提出采集或研究需求即可生成</p>
          <RouterLink to="/" class="btn-primary mt-5">开始一个新对话</RouterLink>
        </div>

        <!-- 卡片 -->
        <ul v-else-if="view === 'grid'" class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(300px,1fr))]">
          <li
            v-for="g in shown"
            :key="g.key"
            class="flex flex-col p-5 transition hover:-translate-y-0.5"
            :class="`card-${toneOf(g)}`"
          >
            <div class="flex items-start gap-2">
              <span class="pill bg-[var(--cs-surface-solid)] accent-ink">{{ artifactKindLabel(g.artifactKind) }}</span>
              <span v-if="g.recordQty != null" class="pill bg-[var(--cs-surface-solid)] text-slate-300">{{ g.recordQty }} 条记录</span>
              <div class="flex-1" />
              <RouterLink
                v-if="g.conversationId"
                :to="{ name: 'chat', params: { id: g.conversationId } }"
                class="round-btn-light !h-9 !w-9"
                aria-label="回到形成该成果的对话"
                title="回到对话"
              >
                <MessageSquare class="h-4 w-4" />
              </RouterLink>
            </div>
            <div class="mt-4 line-clamp-2 min-h-12 text-[16px] leading-6 font-bold tracking-tight text-white" :title="g.name">{{ g.name }}</div>
            <div class="mt-1 text-xs text-slate-300">
              {{ relativeTime(g.createdTime) }} · {{ g.files.length }} 种格式 · {{ formatBytes(totalBytes(g)) }} · {{ qualityLabel(g.quality) }}
            </div>
            <div class="mt-4 flex flex-wrap gap-1.5">
              <button
                v-for="f in g.files"
                :key="f.artifact_id"
                type="button"
                class="pill !px-2.5 !py-1.5 bg-[var(--cs-surface-solid)] text-slate-100 transition hover:-translate-y-px hover:shadow-sm disabled:opacity-50"
                :disabled="busy === f.artifact_id || f.artifact_status !== 'available'"
                :title="`下载 ${f.display_name}（${formatBytes(f.byte_qty)}）`"
                @click="download(f)"
              >
                <Loader2 v-if="busy === f.artifact_id" class="h-3.5 w-3.5 animate-spin" />
                <span v-else class="h-2.5 w-2.5 rounded-full" :style="{ background: dotOf(f) }" />
                {{ fmtLabel(f) }}
                <Download class="h-3 w-3 opacity-60" />
              </button>
            </div>
            <div class="mt-auto flex pt-4">
              <button class="btn-primary btn-sm ml-auto" :disabled="!g.available" @click="openPreview(g)"><Eye class="h-3.5 w-3.5" /> 预览</button>
            </div>
          </li>
        </ul>

        <!-- 列表 -->
        <DataTable v-else :columns="columns" :rows="shown" row-key="key" :page-size="20" empty-text="没有符合条件的成果">
          <template #cell-name="{ row }">
            <span class="flex items-center gap-3">
              <span class="h-9 w-1.5 shrink-0 rounded-full" :style="{ background: `var(--pastel-${toneOf(row)}-dot)` }" />
              <span class="min-w-0">
                <span class="block truncate font-semibold text-white" :title="row.name">{{ row.name }}</span>
                <span class="block text-xs text-slate-500">{{ qualityLabel(row.quality) }}<template v-if="row.recordQty != null"> · {{ row.recordQty }} 条记录</template></span>
              </span>
            </span>
          </template>
          <template #cell-kind="{ row }"><span class="text-slate-300">{{ artifactKindLabel(row.artifactKind) }}</span></template>
          <template #cell-formats="{ row }">
            <span class="flex flex-wrap gap-1">
              <button
                v-for="f in row.files"
                :key="f.artifact_id"
                type="button"
                class="chip !gap-1.5 !px-2.5 !py-0.5 !text-xs"
                :disabled="busy === f.artifact_id || f.artifact_status !== 'available'"
                :title="`下载 ${f.display_name}（${formatBytes(f.byte_qty)}）`"
                @click="download(f)"
              >
                <span class="h-2 w-2 rounded-full" :style="{ background: dotOf(f) }" />{{ fmtLabel(f) }}
              </button>
            </span>
          </template>
          <template #cell-size="{ row }"><span class="tabular-nums text-slate-300">{{ formatBytes(totalBytes(row)) }}</span></template>
          <template #cell-createdTime="{ row }"><span class="tabular-nums text-slate-300">{{ formatTime(row.createdTime) }}</span></template>
          <template #cell-actions="{ row }">
            <span class="inline-flex items-center gap-1">
              <RouterLink
                v-if="row.conversationId"
                :to="{ name: 'chat', params: { id: row.conversationId } }"
                class="icon-btn !h-8 !w-8"
                aria-label="回到对话"
                title="回到对话"
              >
                <MessageSquare class="h-4 w-4" />
              </RouterLink>
              <button class="btn-secondary btn-sm" :disabled="!row.available" @click="openPreview(row)"><Eye class="h-3.5 w-3.5" /> 预览</button>
            </span>
          </template>
        </DataTable>
      </div>
    </div>
    <aside
      v-if="preview"
      class="glass-strong fixed inset-0 z-40 flex w-full flex-col !rounded-none lg:relative lg:inset-auto lg:w-[45%] lg:max-w-4xl lg:!rounded-[28px]"
      aria-label="成果预览"
    >
      <header class="hairline flex items-center gap-3 border-b py-2.5 pr-2.5 pl-5">
        <span class="min-w-0 flex-1 truncate text-sm font-bold">{{ preview.name }}</span>
        <button class="round-btn-light !h-9 !w-9" aria-label="关闭预览" @click="preview = null"><X class="h-4 w-4" /></button>
      </header>
      <div class="min-h-0 flex-1"><ArtifactPanel :artifact-id="preview.id" /></div>
    </aside>
  </div>
</template>
