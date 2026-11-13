import { onBeforeUnmount, ref, type Ref } from 'vue'

/** 响应式媒体查询：返回当前是否匹配 */
export function useMedia(query: string): Ref<boolean> {
  const mq = window.matchMedia(query)
  const matches = ref(mq.matches)
  const on = (e: MediaQueryListEvent) => (matches.value = e.matches)
  mq.addEventListener('change', on)
  onBeforeUnmount(() => mq.removeEventListener('change', on))
  return matches
}

/** 布局断点：≥1280 三栏；1024–1279 抽屉；<1024 单栏 */
export const WIDE_QUERY = '(min-width: 1280px)'
export const MEDIUM_QUERY = '(min-width: 1024px)'
