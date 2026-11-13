<script setup lang="ts">
import { CornerDownRight } from 'lucide-vue-next'
import type { SuggestionsPart } from '@/api/types'
import { useChatActions } from '@/lib/chatActions'

defineProps<{ part: SuggestionsPart }>()
const actions = useChatActions()
</script>

<template>
  <section aria-label="接着问" class="pl-1">
    <div class="mb-2 text-xs font-semibold tracking-wide muted">接着问</div>
    <div class="flex flex-col items-start gap-1.5">
      <button
        v-for="q in part.items"
        :key="q"
        type="button"
        class="follow-up group"
        @click="actions.ask(q)"
      >
        <CornerDownRight class="h-3.5 w-3.5 shrink-0 opacity-50 transition group-hover:opacity-100" />
        <span>{{ q }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.follow-up {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  max-width: 100%;
  padding: 0.45rem 0.9rem;
  border-radius: 999px;
  border: 1px solid var(--cs-line);
  background: var(--cs-surface-solid);
  font-size: 14px;
  text-align: left;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;
}
.follow-up:hover {
  border-color: var(--cs-ink);
}
</style>
