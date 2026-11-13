<script setup lang="ts">
import { computed } from 'vue'
import type { TextPart } from '@/api/types'
import { renderMarkdown } from '@/lib/markdown'
import { usePanelStore } from '@/stores/panel'

const props = defineProps<{ part: TextPart; taskId?: string | null; streaming?: boolean }>()
const panel = usePanelStore()

const html = computed(() => renderMarkdown(props.part.text, props.part.citations?.map((c) => c.n) ?? null))

function onClick(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest('[data-cite]') as HTMLElement | null
  if (!el) return
  const n = Number(el.dataset.cite)
  if (props.taskId) panel.openSources(props.taskId, n)
  else {
    const c = props.part.citations?.find((x) => x.n === n)
    if (c?.url) window.open(c.url, '_blank', 'noopener')
  }
}
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- 已经过 markdown-it(html:false)+DOMPurify 净化 -->
  <div class="prose-cs" @click="onClick" v-html="html" />
  <span v-if="streaming" class="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-brand-300 align-middle" aria-label="生成中" />
</template>
