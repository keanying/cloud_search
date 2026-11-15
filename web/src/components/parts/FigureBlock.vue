<script setup lang="ts">
import { computed } from 'vue'
import { captionHtml, sanitizeSvg } from '@/lib/markdown'

/** 报告配图（```figure）：阶段总览图、结构示意图。SVG 由服务端根据报告内容生成，显示前再净化。 */
const props = defineProps<{ raw: string; fig?: number }>()
const spec = computed(() => {
  try {
    const f = JSON.parse(props.raw) as { kind?: string; caption?: string; sources?: string; svg?: string }
    return f && typeof f.svg === 'string' && f.svg.startsWith('<svg') ? f : null
  } catch {
    return null
  }
})
const svg = computed(() => (spec.value ? sanitizeSvg(spec.value.svg!) : ''))
const caption = computed(() => {
  const f = spec.value
  if (!f) return ''
  const head = `${props.fig ? `图${props.fig}｜` : ''}${f.caption || ''}`
  const sep = /[。？！?!.]$/.test(head) ? '' : '。'
  return captionHtml(f.sources ? `${head}${sep}依据来源${f.sources}` : head)
})
</script>

<template>
  <figure v-if="spec" class="cs-figure not-prose my-5">
    <!-- eslint-disable-next-line vue/no-v-html -- 服务端生成、前端再经 DOMPurify(SVG) 净化 -->
    <div class="figure-svg" role="img" :aria-label="spec.caption" v-html="svg" />
    <!-- eslint-disable-next-line vue/no-v-html -- 已转义，仅插入引用按钮 -->
    <figcaption class="mt-2 text-center text-[12px] leading-5 text-slate-400" v-html="caption" />
  </figure>
</template>

<style scoped>
.figure-svg {
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid var(--cs-line);
  background: #fff;
  box-shadow: var(--cs-shadow);
}
.figure-svg :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
}
</style>
