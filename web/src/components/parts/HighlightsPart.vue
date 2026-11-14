<script setup lang="ts">
import type { HighlightsPart } from '@/api/types'
import { usePanelStore } from '@/stores/panel'
import { fileIdFromUrl } from '@/lib/fileTypes'

const props = defineProps<{ part: HighlightsPart; taskId?: string | null }>()
const panel = usePanelStore()
const TONES = ['mint', 'sky', 'lilac', 'butter'] as const

function open(n: number, url?: string | null) {
  const fid = fileIdFromUrl(url)
  if (fid) return panel.openFile(fid)
  if (props.taskId) panel.openSources(props.taskId, n)
  else if (url) window.open(url, '_blank', 'noopener')
}
</script>

<template>
  <section aria-label="关键数字" class="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
    <button
      v-for="(h, i) in part.items"
      :key="i"
      type="button"
      class="stat-tile text-left"
      :class="`card-${TONES[i % TONES.length]}`"
      :title="`来源 [${h.source_n}]，点击查看原文`"
      @click="open(h.source_n, h.url)"
    >
      <span class="block text-[26px] leading-tight font-bold tracking-tight tabular-nums">
        {{ h.value }}<span v-if="h.unit" class="ml-1 text-sm font-semibold opacity-70">{{ h.unit }}</span>
      </span>
      <span class="mt-1 flex items-center gap-1.5 text-[13px] opacity-80">
        <span class="truncate">{{ h.label }}</span>
        <span class="cite-chip !align-middle">{{ h.source_n }}</span>
      </span>
    </button>
  </section>
</template>

<style scoped>
.stat-tile {
  color: var(--accent-ink);
  padding: 0.9rem 1rem;
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease;
}
.stat-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgb(15 23 42 / 0.08);
}
</style>
