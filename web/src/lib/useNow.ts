import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

/** 每秒更新的当前时间（只在 active 为真时计时，用于进行中的耗时显示） */
export function useNow(active: Ref<boolean>) {
  const now = ref(Date.now())
  let timer: number | undefined
  function sync() {
    window.clearInterval(timer)
    timer = undefined
    if (active.value) {
      now.value = Date.now()
      timer = window.setInterval(() => (now.value = Date.now()), 1000)
    }
  }
  watch(active, sync, { immediate: true })
  onBeforeUnmount(() => window.clearInterval(timer))
  return now
}
