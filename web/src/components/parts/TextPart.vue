<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { Citation, TextPart } from '@/api/types'
import CitePreview from './CitePreview.vue'
import { fileIdFromUrl } from '@/lib/fileTypes'
import { renderMarkdown, splitCharts } from '@/lib/markdown'
import { usePanelStore } from '@/stores/panel'
import ChartBlock from './ChartBlock.vue'

const props = defineProps<{ part: TextPart; taskId?: string | null; streaming?: boolean }>()
const panel = usePanelStore()

const citeNs = computed(() => props.part.citations?.map((c) => c.n) ?? null)
const segments = computed(() =>
  splitCharts(props.part.text).map((s) => (s.kind === 'md' ? { ...s, html: renderMarkdown(s.text, citeNs.value) } : s)),
)

// ---------------------------------------------------------------- 引用悬停预览
const hoverCite = ref<Citation | null>(null)
const hoverEl = ref<HTMLElement | null>(null)
let hideTimer: number | undefined
let showTimer: number | undefined

function citeOf(el: HTMLElement): Citation | null {
  const n = Number(el.dataset.cite)
  return props.part.citations?.find((c) => c.n === n) ?? null
}
function show(el: HTMLElement) {
  window.clearTimeout(hideTimer)
  window.clearTimeout(showTimer)
  const c = citeOf(el)
  if (!c) return
  showTimer = window.setTimeout(() => {
    hoverCite.value = c
    hoverEl.value = el
  }, 180)
}
function hideSoon() {
  window.clearTimeout(showTimer)
  hideTimer = window.setTimeout(() => {
    hoverCite.value = null
    hoverEl.value = null
  }, 160)
}
function onOver(e: Event) {
  const el = (e.target as HTMLElement).closest('[data-cite]') as HTMLElement | null
  if (el) show(el)
}
function onOut(e: Event) {
  if ((e.target as HTMLElement).closest('[data-cite]')) hideSoon()
}
onBeforeUnmount(() => {
  window.clearTimeout(hideTimer)
  window.clearTimeout(showTimer)
})

function openCite(n: number) {
  hoverCite.value = null
  const c = props.part.citations?.find((x) => x.n === n)
  const fid = fileIdFromUrl(c?.url)
  if (fid) panel.openFile(fid) // 引用的是上传的文件：直接预览文件
  else if (props.taskId) panel.openSources(props.taskId, n)
  else if (c?.url) window.open(c.url, '_blank', 'noopener')
}
function openFile(fid: string) {
  hoverCite.value = null
  panel.openFile(fid)
}

function onClick(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest('[data-cite]') as HTMLElement | null
  if (!el) return
  const n = Number(el.dataset.cite)
  hoverCite.value = null
  const c = props.part.citations?.find((x) => x.n === n)
  const fid = fileIdFromUrl(c?.url)
  if (fid) panel.openFile(fid) // 引用的是上传的文件：直接预览文件
  else if (props.taskId) panel.openSources(props.taskId, n)
  else if (c?.url) window.open(c.url, '_blank', 'noopener')
}
</script>

<template>
  <div class="prose-cs" @click="onClick" @mouseover="onOver" @mouseout="onOut" @focusin="onOver" @focusout="onOut">
    <template v-for="(s, i) in segments" :key="i">
      <!-- eslint-disable-next-line vue/no-v-html -- 已经过 markdown-it(html:false)+DOMPurify 净化 -->
      <div v-if="s.kind === 'md'" v-html="(s as { html: string }).html" />
      <ChartBlock v-else :raw="s.raw" />
    </template>
  </div>
  <CitePreview
    :cite="hoverCite"
    :anchor="hoverEl"
    @enter="show(hoverEl!)"
    @leave="hideSoon"
    @open="openCite"
    @open-file="openFile"
  />
  <span v-if="streaming" class="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-brand-300 align-middle" aria-label="生成中" />
</template>
