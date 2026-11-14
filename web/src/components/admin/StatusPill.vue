<script setup lang="ts">
import { computed } from 'vue'

/** 状态胶囊：色点 + 文本，按色调着色（与粉彩卡片一致） */
const props = defineProps<{ tone: 'mint' | 'sky' | 'lilac' | 'butter' | 'peach' | 'gray'; text: string; title?: string }>()
const style = computed(() =>
  props.tone === 'gray'
    ? { background: 'var(--cs-surface-sunken)', color: 'var(--color-slate-300)' }
    : { background: `var(--pastel-${props.tone})`, color: `var(--pastel-${props.tone}-ink)` },
)
const dot = computed(() => (props.tone === 'gray' ? 'var(--color-slate-500)' : `var(--pastel-${props.tone}-dot)`))
</script>

<template>
  <span class="pill" :style="style" :title="title">
    <span class="h-1.5 w-1.5 rounded-full" :style="{ background: dot }" />{{ text }}
  </span>
</template>
