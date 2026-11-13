<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { BarChart3 } from 'lucide-vue-next'
import { buildOption, loadECharts, parseChartSpec } from '@/lib/charts'
import { usePrefsStore } from '@/stores/prefs'

const props = defineProps<{ raw: string }>()
const prefs = usePrefsStore()
const spec = computed(() => parseChartSpec(props.raw))
const el = ref<HTMLElement | null>(null)
const failed = ref(false)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chart: any = null
let ro: ResizeObserver | null = null

async function render() {
  if (!spec.value || !el.value) return
  try {
    const echarts = await loadECharts()
    if (!el.value) return
    chart?.dispose()
    chart = echarts.init(el.value, undefined, { renderer: 'canvas' })
    chart.setOption(buildOption(spec.value, prefs.theme === 'dark'))
  } catch {
    failed.value = true
  }
}

onMounted(() => {
  void render()
  if (el.value && 'ResizeObserver' in window) {
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(el.value)
  }
})
watch(() => [props.raw, prefs.theme], () => void render())
onBeforeUnmount(() => {
  ro?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <figure v-if="spec && !failed" class="cs-chart surface not-prose overflow-hidden rounded-xl p-3">
    <div ref="el" class="h-[300px] w-full" role="img" :aria-label="`图表：${spec.title}`" />
    <figcaption v-if="spec.source" class="mt-1 flex items-center gap-1 text-[11px] text-slate-400">
      <BarChart3 class="h-3 w-3" /> 数据来源：{{ spec.source }}
    </figcaption>
  </figure>
  <pre v-else class="cs-chart overflow-x-auto rounded-xl p-3 text-xs"><code>{{ raw }}</code></pre>
</template>
