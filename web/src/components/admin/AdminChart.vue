<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadECharts } from '@/lib/charts'
import { usePrefsStore } from '@/stores/prefs'

/** 后台图表：传入按主题生成 ECharts 配置的函数；按需加载 ECharts，随容器尺寸变化 */
const props = withDefaults(defineProps<{ option: (dark: boolean) => object; height?: number; label: string }>(), { height: 280 })
const prefs = usePrefsStore()
const el = ref<HTMLElement | null>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chart: any = null
let ro: ResizeObserver | null = null

async function render() {
  if (!el.value) return
  const echarts = await loadECharts()
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value, undefined, { renderer: 'canvas' })
  chart.setOption(props.option(prefs.theme === 'dark'), true)
}
onMounted(() => {
  void render()
  if (el.value && 'ResizeObserver' in window) {
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(el.value)
  }
})
watch(() => [props.option, prefs.theme], () => void render())
onBeforeUnmount(() => {
  ro?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="el" class="w-full" :style="{ height: `${height}px` }" role="img" :aria-label="label" />
</template>
