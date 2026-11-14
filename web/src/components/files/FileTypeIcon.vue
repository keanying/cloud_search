<script setup lang="ts">
import { computed } from 'vue'
import { fileKind } from '@/lib/fileTypes'

const props = defineProps<{ ext: string; size?: 'sm' | 'md' }>()
const kind = computed(() => fileKind(props.ext))
</script>

<template>
  <span
    class="relative flex shrink-0 items-center justify-center rounded-xl"
    :class="[
      size === 'sm' ? 'h-8 w-8' : 'h-10 w-10',
      kind.tone === 'plain' ? 'sunken hairline border text-slate-300' : `card-${kind.tone} accent-ink`,
    ]"
    :title="kind.label"
    aria-hidden="true"
  >
    <component :is="kind.icon" :class="size === 'sm' ? 'h-4 w-4' : 'h-[18px] w-[18px]'" />
  </span>
</template>
