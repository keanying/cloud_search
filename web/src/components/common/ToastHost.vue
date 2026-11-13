<script setup lang="ts">
import { CheckCircle2, Info, X, XCircle } from 'lucide-vue-next'
import { useToastStore } from '@/stores/toast'
const toast = useToastStore()
</script>

<template>
  <div class="pointer-events-none fixed top-4 right-4 z-[100] flex w-80 flex-col gap-2" aria-live="polite">
    <div
      v-for="t in toast.items"
      :key="t.id"
      class="glass-strong pointer-events-auto flex items-start gap-2 px-3 py-2.5 text-sm"
      :class="t.kind === 'error' ? 'border-rose-400/40' : t.kind === 'success' ? 'border-emerald-400/40' : ''"
      role="status"
    >
      <XCircle v-if="t.kind === 'error'" class="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
      <CheckCircle2 v-else-if="t.kind === 'success'" class="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
      <Info v-else class="mt-0.5 h-4 w-4 shrink-0 text-brand-300" />
      <span class="flex-1 text-slate-100">{{ t.text }}</span>
      <button class="text-slate-400 hover:text-white" aria-label="关闭提示" @click="toast.dismiss(t.id)">
        <X class="h-4 w-4" />
      </button>
    </div>
  </div>
</template>
