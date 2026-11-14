<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { PenLine } from 'lucide-vue-next'
import type { DraftPart } from '@/api/types'
import { renderMarkdown } from '@/lib/markdown'

/** 撰写中的实时草稿：像文档一样边写边显示，自动跟随到最新内容；完成后由最终成果替代 */
const props = defineProps<{ part: DraftPart }>()
const box = ref<HTMLElement | null>(null)
const follow = ref(true)
const html = computed(() => renderMarkdown(props.part.text || '', null))

function onScroll() {
  const el = box.value
  if (!el) return
  follow.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40 // 用户往上翻时不再自动跟随
}
watch(
  () => props.part.text,
  async () => {
    await nextTick()
    if (follow.value && box.value) box.value.scrollTo({ top: box.value.scrollHeight, behavior: 'smooth' })
  },
)
</script>

<template>
  <section class="draft surface overflow-hidden" aria-live="polite" :aria-label="`正在撰写：${part.title}`">
    <header class="flex items-center gap-2.5 border-b border-[var(--cs-line)] px-5 py-3">
      <span class="relative flex h-7 w-7 items-center justify-center rounded-full card-lilac">
        <PenLine class="h-3.5 w-3.5 accent-ink" />
        <span class="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--pastel-mint-dot)] motion-reduce:animate-none" />
      </span>
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-semibold text-white">{{ part.title || '正在撰写' }}</div>
        <div class="text-xs text-slate-400 tabular-nums">
          正在撰写{{ part.kind === 'report' ? '报告' : '回答' }} · 已写 {{ part.chars.toLocaleString() }} 字
        </div>
      </div>
    </header>
    <div ref="box" class="draft-body relative px-6 py-5" :class="part.kind === 'report' ? 'max-h-[460px] overflow-y-auto' : ''" @scroll="onScroll">
      <!-- eslint-disable-next-line vue/no-v-html -- 已经过 markdown-it(html:false)+DOMPurify 净化 -->
      <div class="prose-cs cs-draft-writing" v-html="html" />
    </div>
  </section>
</template>

<style>
/* 光标紧跟在最后一段文字末尾（全局选择器：内容来自 v-html） */
.cs-draft-writing > :last-child:not(ul):not(ol)::after,
.cs-draft-writing > ul:last-child > li:last-child::after,
.cs-draft-writing > ol:last-child > li:last-child::after {
  content: '';
  display: inline-block;
  width: 0.5rem;
  height: 1.05rem;
  margin-left: 3px;
  vertical-align: text-bottom;
  border-radius: 2px;
  background: var(--cs-ink);
  animation: cs-caret-blink 1.1s ease-in-out infinite;
}
@keyframes cs-caret-blink {
  0%,
  45% {
    opacity: 1;
  }
  55%,
  100% {
    opacity: 0.15;
  }
}
@media (prefers-reduced-motion: reduce) {
  .cs-draft-writing > :last-child::after,
  .cs-draft-writing li:last-child::after {
    animation: none;
  }
}
</style>
