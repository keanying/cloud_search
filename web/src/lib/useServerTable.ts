import { onMounted, reactive, ref, shallowRef, watch, type Ref } from 'vue'
import type { Paged } from '@/api/types'
import { useToastStore } from '@/stores/toast'

/**
 * 服务端分页表格：page / size / 筛选条件变化时重新取数；筛选变化回到第 1 页。
 * 较早请求晚到时丢弃（只保留最后一次请求的结果）。
 */
export function useServerTable<T, F extends Record<string, string>>(
  fetcher: (q: F & { page: number; size: number }) => Promise<Paged<T>>,
  initialFilters: F,
  initialSize = 20,
) {
  const toast = useToastStore()
  const rows = shallowRef<T[]>([])
  const total = ref(0)
  const page = ref(1)
  const size = ref(initialSize)
  const loading = ref(false)
  const filters = reactive({ ...initialFilters }) as F
  let seq = 0

  async function load() {
    const my = ++seq
    loading.value = true
    try {
      const res = await fetcher({ ...(filters as F), page: page.value, size: size.value })
      if (my !== seq) return
      rows.value = res.items
      total.value = res.total
    } catch (e) {
      if (my === seq) toast.error(e, '加载失败')
    } finally {
      if (my === seq) loading.value = false
    }
  }

  watch([page, size], () => void load())
  watch(
    () => ({ ...filters }),
    () => {
      if (page.value !== 1) page.value = 1
      else void load()
    },
  )
  onMounted(load)

  return { rows: rows as Ref<T[]>, total, page, size, loading, filters, reload: load }
}
