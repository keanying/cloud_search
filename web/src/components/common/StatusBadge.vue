<script setup lang="ts">
import { computed } from 'vue'
import type { Tone } from '@/lib/format'
const props = defineProps<{ tone?: Tone; pulse?: boolean; emoji?: string }>()
const cls = computed(() => {
  switch (props.tone) {
    case 'info':
      return 'card-sky accent-ink'
    case 'success':
      return 'card-mint accent-ink'
    case 'warning':
      return 'card-butter accent-ink'
    case 'danger':
      return 'card-peach accent-ink'
    default:
      return 'sunken text-slate-300 border hairline'
  }
})
</script>

<template>
  <span class="pill !rounded-full" :class="cls">
    <span v-if="emoji" aria-hidden="true">{{ emoji }}</span>
    <span v-else-if="pulse" class="cs-ping h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
    <slot />
  </span>
</template>
