<script setup lang="ts">
import { computed } from 'vue'
import type { Tone } from '@/lib/format'
const props = defineProps<{ tone?: Tone; pulse?: boolean }>()
const cls = computed(() => {
  switch (props.tone) {
    case 'info':
      return 'border-brand-400/40 bg-brand-500/15 text-brand-300'
    case 'success':
      return 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200'
    case 'warning':
      return 'border-amber-400/40 bg-amber-500/15 text-amber-200'
    case 'danger':
      return 'border-rose-400/40 bg-rose-500/15 text-rose-200'
    default:
      return 'border-white/15 bg-white/5 text-slate-300'
  }
})
</script>

<template>
  <span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap" :class="cls">
    <span v-if="pulse" class="h-1.5 w-1.5 animate-pulse rounded-full bg-current" aria-hidden="true" />
    <slot />
  </span>
</template>
