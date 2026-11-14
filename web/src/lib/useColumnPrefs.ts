import { computed, isRef, ref, watch, type Ref } from 'vue'
import type { Column } from '@/components/common/DataTable.vue'

/**
 * 表格列显示偏好（按表记忆在本地）：隐藏的列 + 密度。
 * 固定列（fixed）和标记 required 的列不可隐藏。
 */
export function useColumnPrefs(key: string, columns: Ref<Column[]> | Column[], required: string[] = []) {
  const all = computed(() => (isRef(columns) ? columns.value : columns))
  const storeKey = `cs_cols_${key}`
  let saved: { hidden?: string[]; density?: 'default' | 'compact' } = {}
  try {
    saved = JSON.parse(localStorage.getItem(storeKey) || '{}')
  } catch {
    saved = {}
  }
  const hidden = ref<string[]>(saved.hidden ?? [])
  const density = ref<'default' | 'compact'>(saved.density ?? 'default')
  watch([hidden, density], () => localStorage.setItem(storeKey, JSON.stringify({ hidden: hidden.value, density: density.value })), {
    deep: true,
  })
  const locked = computed(() => new Set([...required, ...all.value.filter((c) => c.fixed).map((c) => c.key)]))
  const visible = computed(() => all.value.filter((c) => locked.value.has(c.key) || !hidden.value.includes(c.key)))
  /** 可切换显示的列（列设置菜单） */
  const toggleable = computed(() => all.value.filter((c) => !locked.value.has(c.key) && c.title))
  return { hidden, density, visible, toggleable }
}
