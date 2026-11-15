<script setup lang="ts">
import { computed, ref } from 'vue'
import { EyeOff, Search } from 'lucide-vue-next'
import { usePanelStore } from '@/stores/panel'

/**
 * 数据表预览（CSV / Excel 成果）：统计条、搜索、空列折叠、列填充率、数字右对齐、来源序号可点击、长文本折叠。
 * compact：对话卡片里的小预览（只显示前几行几列，不带工具条）。
 */
const props = withDefaults(
  defineProps<{
    columns: string[]
    rows: unknown[][]
    totalRows?: number | null
    taskId?: string | null
    compact?: boolean
    maxRows?: number
    maxCols?: number
  }>(),
  { totalRows: null, taskId: null, compact: false, maxRows: 5, maxCols: 6 },
)
const panel = usePanelStore()
const q = ref('')
const hideEmpty = ref(true)
const expanded = ref<Set<number>>(new Set())

const isEmpty = (v: unknown) => v == null || (typeof v === 'string' && v.trim() === '')
const NUM = /^[-+]?[\d,，]*\.?\d+(%|％)?$/
const SOURCE_COL = /^(来源序号|来源编号|来源)$/
const NOTE_COL = /^(缺失说明|说明|备注)$/

const stats = computed(() =>
  props.columns.map((c, j) => {
    const vals = props.rows.map((r) => r[j])
    const filled = vals.filter((v) => !isEmpty(v))
    const numeric = filled.length > 0 && filled.filter((v) => NUM.test(String(v).trim())).length / filled.length >= 0.7
    return { name: c, filled: filled.length, rate: props.rows.length ? filled.length / props.rows.length : 0, numeric }
  }),
)
const emptyCols = computed(() => stats.value.filter((s) => s.filled === 0).length)
const visibleCols = computed(() => {
  let idx = props.columns.map((_, j) => j)
  if (hideEmpty.value || props.compact) idx = idx.filter((j) => stats.value[j].filled > 0 || SOURCE_COL.test(props.columns[j]))
  return props.compact ? idx.slice(0, props.maxCols) : idx
})
const filtered = computed(() => {
  const kw = q.value.trim().toLowerCase()
  const list = props.rows.map((r, i) => ({ r, i }))
  const hit = kw ? list.filter(({ r }) => r.some((v) => !isEmpty(v) && String(v).toLowerCase().includes(kw))) : list
  return props.compact ? hit.slice(0, props.maxRows) : hit
})
const fillRate = computed(() => {
  const cells = props.rows.length * props.columns.length
  if (!cells) return 0
  return Math.round((stats.value.reduce((n, s) => n + s.filled, 0) / cells) * 100)
})

function sourceNos(v: unknown): number[] {
  return String(v ?? '')
    .split(/[,，、\s]+/)
    .map((x) => Number(x))
    .filter((n) => Number.isInteger(n) && n > 0)
}
function isUrl(v: unknown) {
  return typeof v === 'string' && /^https?:\/\//.test(v)
}
function host(v: string) {
  try {
    return new URL(v).hostname.replace(/^www\./, '')
  } catch {
    return v
  }
}
function fmt(v: unknown) {
  if (typeof v === 'number') return v.toLocaleString('zh-CN')
  if (v instanceof Date) return v.toISOString().slice(0, 10)
  return String(v)
}
function toggle(i: number) {
  const s = new Set(expanded.value)
  if (s.has(i)) s.delete(i)
  else s.add(i)
  expanded.value = s
}
function openSource(n: number) {
  if (props.taskId) panel.openSources(props.taskId, n)
}
</script>

<template>
  <div class="dpt" :class="compact ? 'dpt-compact' : ''">
    <div v-if="!compact" class="mb-2 flex flex-wrap items-center gap-2">
      <span class="pill bg-[var(--cs-surface-solid)] text-slate-200">{{ (totalRows ?? rows.length).toLocaleString('zh-CN') }} 行 · {{ columns.length }} 列</span>
      <span class="pill" :class="fillRate >= 70 ? 'card-mint accent-ink' : fillRate >= 40 ? 'card-butter accent-ink' : 'card-peach accent-ink'" title="非空单元格占比">
        已填 {{ fillRate }}%
      </span>
      <button v-if="emptyCols" type="button" class="pill bg-[var(--cs-surface-solid)] text-slate-300 hover:text-white" @click="hideEmpty = !hideEmpty">
        <EyeOff class="h-3 w-3" /> {{ hideEmpty ? `已隐藏 ${emptyCols} 个空列` : '隐藏空列' }}
      </button>
      <div class="flex-1" />
      <label class="relative">
        <Search class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
        <input v-model="q" class="input !w-48 !rounded-full !py-1.5 !pl-8 !text-xs" placeholder="在表格中搜索" aria-label="在表格中搜索" />
      </label>
    </div>

    <div class="dpt-wrap">
      <table class="dpt-table">
        <thead>
          <tr>
            <th class="dpt-sticky dpt-idx">#</th>
            <th v-for="(j, k) in visibleCols" :key="j" :class="[stats[j].numeric ? 'text-right' : '', k === 0 ? 'dpt-sticky dpt-first' : '']">
              <span class="block whitespace-nowrap">{{ columns[j] }}</span>
              <span v-if="!compact" class="dpt-fill" :title="`已填 ${stats[j].filled}/${rows.length}`">
                <i :style="{ width: `${Math.round(stats[j].rate * 100)}%` }" :class="stats[j].rate < 0.4 ? 'low' : ''" />
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="{ r, i } in filtered" :key="i" :class="expanded.has(i) ? 'is-open' : ''" @click="!compact && toggle(i)">
            <td class="dpt-sticky dpt-idx">{{ i + 1 }}</td>
            <td
              v-for="(j, k) in visibleCols"
              :key="j"
              :class="[stats[j].numeric ? 'text-right tabular-nums' : '', k === 0 ? 'dpt-sticky dpt-first font-medium text-white' : '', NOTE_COL.test(columns[j]) ? 'dpt-note' : '']"
              :title="isEmpty(r[j]) ? '空' : fmt(r[j])"
            >
              <span v-if="isEmpty(r[j])" class="text-slate-600">—</span>
              <span v-else-if="SOURCE_COL.test(columns[j]) && sourceNos(r[j]).length" class="inline-flex flex-wrap gap-0.5">
                <button v-for="n in sourceNos(r[j])" :key="n" type="button" class="cite-chip !m-0 !align-middle" :aria-label="`查看来源 ${n}`" @click.stop="openSource(n)">{{ n }}</button>
              </span>
              <a v-else-if="isUrl(r[j])" :href="String(r[j])" target="_blank" rel="noopener noreferrer nofollow" class="text-brand-300 hover:underline" @click.stop>{{ host(String(r[j])) }}</a>
              <span v-else class="dpt-text">{{ fmt(r[j]) }}</span>
            </td>
          </tr>
          <tr v-if="!filtered.length">
            <td :colspan="visibleCols.length + 1" class="py-6 text-center text-slate-500">{{ q ? '没有匹配的行' : '没有数据' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.dpt-wrap {
  overflow: auto;
  max-height: 100%;
  border-radius: 16px;
  border: 1px solid var(--cs-line);
  background: var(--cs-surface-solid);
}
.dpt:not(.dpt-compact) .dpt-wrap {
  max-height: calc(100vh - 260px);
}
.dpt-table {
  width: max-content;
  min-width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12.5px;
  line-height: 1.5;
}
.dpt-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 8px 12px 6px;
  text-align: left;
  font-weight: 600;
  font-size: 12px;
  color: var(--color-slate-300);
  background: var(--color-ink-800);
  border-bottom: 1px solid var(--cs-line-strong);
}
.dpt-table td {
  max-width: 260px;
  padding: 7px 12px;
  vertical-align: top;
  color: var(--color-slate-200);
  border-bottom: 1px solid var(--cs-line);
  background: var(--cs-surface-solid);
}
.dpt-table tbody tr:nth-child(even) td {
  background: color-mix(in srgb, var(--color-ink-800) 45%, var(--cs-surface-solid));
}
.dpt-table tbody tr:hover td {
  background: color-mix(in srgb, var(--cs-ink) 7%, var(--cs-surface-solid));
}
.dpt:not(.dpt-compact) .dpt-table tbody tr {
  cursor: pointer;
}
.dpt-text {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-word;
}
.is-open .dpt-text {
  -webkit-line-clamp: unset;
}
.dpt-note .dpt-text {
  -webkit-line-clamp: 2;
}
.dpt-note {
  font-size: 11.5px;
  color: var(--color-slate-400) !important;
}
.dpt-sticky {
  position: sticky;
  z-index: 1;
}
th.dpt-sticky {
  z-index: 3;
}
.dpt-idx {
  left: 0;
  width: 36px;
  min-width: 36px;
  text-align: right !important;
  color: var(--color-slate-500) !important;
  font-variant-numeric: tabular-nums;
}
.dpt-first {
  left: 36px;
  box-shadow: 1px 0 0 var(--cs-line);
}
.dpt-fill {
  display: block;
  margin-top: 4px;
  height: 3px;
  width: 100%;
  min-width: 40px;
  border-radius: 999px;
  background: var(--cs-line);
  overflow: hidden;
}
.dpt-fill i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--cs-ink-grad);
}
.dpt-fill i.low {
  background: var(--pastel-peach-dot);
}
.dpt-compact .dpt-table td {
  max-width: 200px;
}
.dpt-compact .dpt-text {
  -webkit-line-clamp: 2;
}
</style>
