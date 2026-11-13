<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'
import type { ErrorPart } from '@/api/types'
defineProps<{ part: ErrorPart }>()
</script>

<template>
  <div class="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2.5 text-sm" role="alert">
    <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
    <div>
      <div class="text-rose-100">{{ part.message }}</div>
      <div v-if="part.code" class="mt-0.5 font-mono text-xs text-rose-300/70">{{ part.code }}</div>
    </div>
  </div>
</template>
