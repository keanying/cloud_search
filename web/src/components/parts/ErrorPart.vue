<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'
import type { ErrorPart } from '@/api/types'
defineProps<{ part: ErrorPart }>()
</script>

<template>
  <div class="card-peach flex items-start gap-3 p-4 text-sm" role="alert">
    <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--cs-surface-solid)]">
      <AlertTriangle class="h-4 w-4 accent-ink" />
    </span>
    <div class="pt-1">
      <div class="font-semibold text-white">{{ part.message }}</div>
      <div v-if="part.code" class="mt-0.5 font-mono text-xs accent-ink opacity-80">{{ part.code }}</div>
    </div>
  </div>
</template>
