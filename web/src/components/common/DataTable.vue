<script setup lang="ts" generic="T extends object">
/**
 * 数据表格（参照 Semi Design Table）：浅色表头、行悬停、排序、分页、空状态、左右固定列、紧凑/默认密度。
 *
 * - 单元格渲染：具名插槽 #cell-<key>="{ row, value, index }"；没有插槽时显示 row[key]
 * - 服务端分页：传 total 并绑定 v-model:page / v-model:size；不传 total 时在前端分页（pageSize>0 时）
 * - 排序：v-model:sort；serverSort=true 时只发出排序变化，由父组件重新取数
 * - 固定列：列上 fixed: 'left' | 'right'，需要给出数值 width
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Inbox, Rows3, Rows4 } from 'lucide-vue-next'

export interface Column {
  key: string
  title: string
  width?: number
  minWidth?: number
  align?: 'left' | 'center' | 'right'
  sortable?: boolean
  fixed?: 'left' | 'right'
  /** 单行省略（悬停显示全文） */
  ellipsis?: boolean
}
export interface SortState {
  key: string
  order: 'asc' | 'desc'
}

const props = withDefaults(
  defineProps<{
    columns: Column[]
    rows: T[]
    rowKey: keyof T | ((row: T) => string)
    loading?: boolean
    /** 服务端分页的总条数；不传则前端分页 */
    total?: number
    /** 前端分页时每页条数；0 表示不分页 */
    pageSize?: number
    serverSort?: boolean
    rowClickable?: boolean
    emptyText?: string
    emptyDesc?: string
    showDensity?: boolean
    /** 去掉外框（嵌入卡片内） */
    bare?: boolean
    sizes?: number[]
    /** 表体最大高度（如 '60vh'），设置后表头吸顶 */
    maxHeight?: string
    /** 高亮的行（如当前在抽屉中查看的行） */
    activeKey?: string | null
  }>(),
  {
    loading: false,
    total: undefined,
    pageSize: 0,
    serverSort: false,
    rowClickable: false,
    emptyText: '暂无数据',
    emptyDesc: '',
    showDensity: false,
    bare: false,
    sizes: () => [10, 20, 50],
    maxHeight: undefined,
    activeKey: null,
  },
)
const emit = defineEmits<{ rowClick: [row: T] }>()
const page = defineModel<number>('page', { default: 1 })
const size = defineModel<number>('size', { default: 20 })
const sort = defineModel<SortState | null>('sort', { default: null })
const density = defineModel<'default' | 'compact'>('density', { default: 'default' })

const scroller = ref<HTMLElement | null>(null)
const scrolledLeft = ref(false)
const scrolledRight = ref(true)
function onScroll() {
  const el = scroller.value
  if (!el) return
  scrolledLeft.value = el.scrollLeft > 2
  scrolledRight.value = el.scrollLeft + el.clientWidth >= el.scrollWidth - 2
}

let ro: ResizeObserver | null = null
onMounted(() => {
  onScroll()
  if (scroller.value && 'ResizeObserver' in window) {
    ro = new ResizeObserver(onScroll)
    ro.observe(scroller.value)
  }
})
onBeforeUnmount(() => ro?.disconnect())
watch(
  () => props.rows,
  () => void nextTick(onScroll),
)

const keyOf = (row: T, i: number): string =>
  typeof props.rowKey === 'function' ? props.rowKey(row) : String((row as Record<string, unknown>)[props.rowKey as string] ?? i)
const valueOf = (row: T, key: string): unknown => (row as Record<string, unknown>)[key]

const server = computed(() => props.total !== undefined)
const sorted = computed(() => {
  if (!sort.value || props.serverSort) return props.rows
  const { key, order } = sort.value
  const dir = order === 'asc' ? 1 : -1
  return [...props.rows].sort((a, b) => {
    const x = valueOf(a, key)
    const y = valueOf(b, key)
    if (x == null && y == null) return 0
    if (x == null) return 1
    if (y == null) return -1
    if (typeof x === 'number' && typeof y === 'number') return (x - y) * dir
    return String(x).localeCompare(String(y), 'zh-CN') * dir
  })
})
const clientPageSize = computed(() => (server.value ? 0 : props.pageSize))
const totalCount = computed(() => (server.value ? (props.total ?? 0) : props.rows.length))
const effSize = computed(() => (server.value ? size.value : clientPageSize.value))
const pageCount = computed(() => (effSize.value > 0 ? Math.max(1, Math.ceil(totalCount.value / effSize.value)) : 1))
const visible = computed(() => {
  if (server.value || !clientPageSize.value) return sorted.value
  const start = (page.value - 1) * clientPageSize.value
  return sorted.value.slice(start, start + clientPageSize.value)
})
const showPager = computed(() => effSize.value > 0 && totalCount.value > 0)

function toggleSort(c: Column) {
  if (!c.sortable) return
  if (!sort.value || sort.value.key !== c.key) sort.value = { key: c.key, order: 'desc' }
  else if (sort.value.order === 'desc') sort.value = { key: c.key, order: 'asc' }
  else sort.value = null
  page.value = 1
}
function go(p: number) {
  page.value = Math.min(Math.max(1, p), pageCount.value)
}
function setSize(n: number) {
  size.value = n
  page.value = 1
}

/** 页码：1 … 4 5 6 … 20 */
const pages = computed<(number | '…')[]>(() => {
  const n = pageCount.value
  const c = page.value
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1)
  const out: (number | '…')[] = [1]
  const lo = Math.max(2, c - 1)
  const hi = Math.min(n - 1, c + 1)
  if (lo > 2) out.push('…')
  for (let i = lo; i <= hi; i++) out.push(i)
  if (hi < n - 1) out.push('…')
  out.push(n)
  return out
})

/** 固定列的偏移量 */
const offsets = computed(() => {
  const left: Record<string, number> = {}
  const right: Record<string, number> = {}
  let acc = 0
  for (const c of props.columns) {
    if (c.fixed === 'left') {
      left[c.key] = acc
      acc += c.width ?? 120
    }
  }
  acc = 0
  for (const c of [...props.columns].reverse()) {
    if (c.fixed === 'right') {
      right[c.key] = acc
      acc += c.width ?? 120
    }
  }
  return { left, right }
})
const lastLeft = computed(() => [...props.columns].reverse().find((c) => c.fixed === 'left')?.key)
const firstRight = computed(() => props.columns.find((c) => c.fixed === 'right')?.key)

function cellStyle(c: Column): Record<string, string> {
  const s: Record<string, string> = {}
  if (c.width) s.width = `${c.width}px`
  if (c.minWidth) s.minWidth = `${c.minWidth}px`
  if (c.fixed === 'left') s.left = `${offsets.value.left[c.key]}px`
  if (c.fixed === 'right') s.right = `${offsets.value.right[c.key]}px`
  return s
}
function cellClass(c: Column) {
  return [
    c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : 'text-left',
    c.fixed ? 'dt-fixed' : '',
    c.key === lastLeft.value && scrolledLeft.value ? 'dt-shadow-l' : '',
    c.key === firstRight.value && !scrolledRight.value ? 'dt-shadow-r' : '',
  ]
}
const skeletonRows = computed(() => Math.min(effSize.value || 6, 8))
</script>

<template>
  <div class="dt" :class="[bare ? '' : 'surface overflow-hidden', density === 'compact' ? 'dt-compact' : '']">
    <div ref="scroller" class="dt-scroll" :style="maxHeight ? { maxHeight } : undefined" @scroll.passive="onScroll">
      <table class="dt-table">
        <colgroup>
          <col v-for="c in columns" :key="c.key" :style="c.width ? { width: `${c.width}px` } : undefined" />
        </colgroup>
        <thead>
          <tr>
            <th
              v-for="c in columns"
              :key="c.key"
              scope="col"
              :style="cellStyle(c)"
              :class="[cellClass(c), c.sortable ? 'dt-sortable' : '']"
              :aria-sort="sort?.key === c.key ? (sort.order === 'asc' ? 'ascending' : 'descending') : undefined"
              @click="toggleSort(c)"
            >
              <span class="inline-flex items-center gap-1" :class="c.align === 'right' ? 'flex-row-reverse' : ''">
                <slot :name="`header-${c.key}`" :column="c">{{ c.title }}</slot>
                <template v-if="c.sortable">
                  <ArrowUp v-if="sort?.key === c.key && sort.order === 'asc'" class="h-3 w-3 text-white" />
                  <ArrowDown v-else-if="sort?.key === c.key" class="h-3 w-3 text-white" />
                  <ChevronsUpDown v-else class="h-3 w-3 opacity-40" />
                </template>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="loading && !rows.length">
            <tr v-for="i in skeletonRows" :key="`sk-${i}`" class="dt-row">
              <td v-for="c in columns" :key="c.key" :style="cellStyle(c)" :class="cellClass(c)">
                <span class="dt-skel" :style="{ width: `${40 + ((i * 17 + c.key.length * 11) % 45)}%` }" />
              </td>
            </tr>
          </template>
          <template v-else>
            <tr
              v-for="(row, i) in visible"
              :key="keyOf(row, i)"
              class="dt-row"
              :class="[rowClickable ? 'cursor-pointer' : '', activeKey && keyOf(row, i) === activeKey ? 'dt-row-on' : '']"
              @click="rowClickable && emit('rowClick', row)"
            >
              <td v-for="c in columns" :key="c.key" :style="cellStyle(c)" :class="cellClass(c)">
                <slot :name="`cell-${c.key}`" :row="row" :value="valueOf(row, c.key)" :index="i">
                  <span
                    :class="c.ellipsis ? 'block truncate' : ''"
                    :title="c.ellipsis ? String(valueOf(row, c.key) ?? '') : undefined"
                  >{{ valueOf(row, c.key) ?? '—' }}</span>
                </slot>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-if="!loading && !rows.length" class="flex flex-col items-center px-6 py-14 text-center">
        <slot name="empty">
          <span class="flex h-12 w-12 items-center justify-center rounded-full sunken"><Inbox class="h-5 w-5 text-slate-400" /></span>
          <div class="mt-3 text-sm font-semibold text-slate-200">{{ emptyText }}</div>
          <div v-if="emptyDesc" class="mt-0.5 text-xs text-slate-500">{{ emptyDesc }}</div>
        </slot>
      </div>
      <div v-if="loading && rows.length" class="dt-loading-bar" aria-hidden="true" />
    </div>

    <footer v-if="showPager || showDensity" class="dt-footer">
      <span class="text-xs text-slate-400">共 {{ totalCount.toLocaleString('zh-CN') }} 条</span>
      <button
        v-if="showDensity"
        type="button"
        class="icon-btn !h-7 !w-7"
        :title="density === 'compact' ? '默认密度' : '紧凑密度'"
        :aria-label="density === 'compact' ? '切换为默认密度' : '切换为紧凑密度'"
        @click="density = density === 'compact' ? 'default' : 'compact'"
      >
        <Rows3 v-if="density === 'compact'" class="h-3.5 w-3.5" />
        <Rows4 v-else class="h-3.5 w-3.5" />
      </button>
      <div class="flex-1" />
      <template v-if="showPager">
        <nav class="flex items-center gap-1" aria-label="分页">
          <button type="button" class="dt-page" :disabled="page <= 1" aria-label="上一页" @click="go(page - 1)">
            <ChevronLeft class="h-3.5 w-3.5" />
          </button>
          <template v-for="(p, i) in pages" :key="`${p}-${i}`">
            <span v-if="p === '…'" class="px-1 text-xs text-slate-500">…</span>
            <button
              v-else
              type="button"
              class="dt-page"
              :class="p === page ? 'dt-page-on' : ''"
              :aria-current="p === page ? 'page' : undefined"
              @click="go(p)"
            >
              {{ p }}
            </button>
          </template>
          <button type="button" class="dt-page" :disabled="page >= pageCount" aria-label="下一页" @click="go(page + 1)">
            <ChevronRight class="h-3.5 w-3.5" />
          </button>
        </nav>
        <select
          v-if="server"
          class="dt-size"
          :value="size"
          aria-label="每页条数"
          @change="setSize(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="n in sizes" :key="n" :value="n">{{ n }} 条/页</option>
        </select>
      </template>
    </footer>
  </div>
</template>

<style scoped>
.dt-scroll {
  position: relative;
  overflow: auto;
}
.dt-table {
  width: 100%;
  min-width: max-content;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;
}
.dt-table th,
.dt-table td {
  padding: 0.85rem 1rem;
  vertical-align: middle;
  border-bottom: 1px solid var(--cs-line);
  background-color: var(--cs-surface-solid);
}
.dt-compact .dt-table th,
.dt-compact .dt-table td {
  padding: 0.5rem 0.85rem;
}
.dt-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background-color: var(--cs-surface-sunken);
  font-size: 12px;
  font-weight: 600;
  color: var(--color-slate-400);
  white-space: nowrap;
}
.dt-sortable {
  cursor: pointer;
  user-select: none;
}
.dt-sortable:hover {
  color: var(--color-white);
}
.dt-row:hover td {
  background-color: color-mix(in srgb, var(--cs-surface-sunken) 70%, var(--cs-line-strong));
}
.dt-row:last-child td {
  border-bottom: 0;
}
.dt-fixed {
  position: sticky;
  z-index: 1;
}
thead .dt-fixed {
  z-index: 3;
}
.dt-shadow-l {
  box-shadow: 8px 0 10px -8px rgb(0 0 0 / 0.18);
}
.dt-shadow-r {
  box-shadow: -8px 0 10px -8px rgb(0 0 0 / 0.18);
}
.dt-skel {
  display: block;
  height: 0.7rem;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--cs-line) 0%, var(--cs-line-strong) 50%, var(--cs-line) 100%);
  background-size: 200% 100%;
  animation: dt-shimmer 1.2s ease-in-out infinite;
}
@keyframes dt-shimmer {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}
.dt-loading-bar {
  position: absolute;
  inset: 0 0 auto 0;
  height: 2px;
  background: var(--pastel-mint-dot);
  animation: dt-load 1s ease-in-out infinite alternate;
  transform-origin: left;
}
@keyframes dt-load {
  from {
    transform: scaleX(0.1);
  }
  to {
    transform: scaleX(0.9);
  }
}
.dt-footer {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  border-top: 1px solid var(--cs-line);
}
.dt-page {
  display: inline-flex;
  min-width: 1.85rem;
  height: 1.85rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 0 0.45rem;
  font-size: 13px;
  color: var(--color-slate-300);
  font-variant-numeric: tabular-nums;
}
.dt-page:hover:not(:disabled) {
  background: var(--cs-line);
}
.dt-page:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.dt-page-on {
  background: var(--cs-ink) !important;
  color: var(--cs-on-ink) !important;
  font-weight: 600;
}
.dt-size {
  border: 1px solid var(--cs-line-strong);
  background: var(--cs-input);
  border-radius: 999px;
  padding: 0.25rem 0.6rem;
  font-size: 12px;
  color: var(--color-slate-200);
}
@media (prefers-reduced-motion: reduce) {
  .dt-skel,
  .dt-loading-bar {
    animation: none;
  }
}
</style>
