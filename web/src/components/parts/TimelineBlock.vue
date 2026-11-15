<script setup lang="ts">
import { computed } from 'vue'
import { parseTimeline } from '@/lib/markdown'

/** 报告里的时间轴（```timeline 代码块）：日期 · 事件 · 来源；图注“图n｜标题” */
const props = defineProps<{ raw: string; fig?: number }>()
const spec = computed(() => parseTimeline(props.raw))
</script>

<template>
  <figure v-if="spec" class="cs-timeline surface not-prose my-4 rounded-2xl px-4 pt-4 pb-3">
    <ol class="relative">
      <li v-for="(it, i) in spec.items" :key="i" class="tl-row">
        <span class="tl-date">{{ it.date }}</span>
        <span class="tl-dot" aria-hidden="true" />
        <span class="min-w-0 flex-1 text-[14px] leading-6 text-slate-200">
          <b class="font-semibold text-white">{{ it.title }}</b>
          <span v-if="it.detail" class="text-slate-400">　{{ it.detail }}</span>
          <button v-if="it.source_n" type="button" class="cite-chip" :data-cite="it.source_n" :aria-label="`查看来源 ${it.source_n}`">{{ it.source_n }}</button>
        </span>
      </li>
    </ol>
    <figcaption class="mt-2 text-center text-[12px] text-slate-400">
      <template v-if="fig">图{{ fig }}｜</template>{{ spec.title || '关键时间节点' }}
    </figcaption>
  </figure>
  <pre v-else class="overflow-x-auto rounded-xl p-3 text-xs"><code>{{ raw }}</code></pre>
</template>

<style scoped>
.tl-row {
  position: relative;
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding-bottom: 0.6rem;
}
.tl-row::before {
  content: '';
  position: absolute;
  left: calc(5.5rem + 0.75rem + 4px);
  top: 0.9rem;
  bottom: -0.2rem;
  width: 2px;
  background: linear-gradient(color-mix(in srgb, var(--cs-ink) 45%, transparent), color-mix(in srgb, var(--cs-ink) 15%, transparent));
}
.tl-row:last-child::before {
  display: none;
}
.tl-date {
  width: 5.5rem;
  flex: none;
  text-align: right;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--color-brand-300);
}
.tl-dot {
  position: relative;
  top: 1px;
  height: 10px;
  width: 10px;
  flex: none;
  border-radius: 999px;
  background: var(--cs-ink-grad);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--cs-ink) 18%, transparent);
}
</style>
