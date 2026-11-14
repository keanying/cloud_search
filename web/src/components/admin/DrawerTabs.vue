<script setup lang="ts" generic="V extends string">
/** 抽屉内的标签页 */
defineProps<{ tabs: { value: V; label: string; count?: number | null }[] }>()
const model = defineModel<V>({ required: true })
</script>

<template>
  <div class="flex gap-1 border-b border-[var(--cs-line)] px-4" role="tablist">
    <button
      v-for="t in tabs"
      :key="t.value"
      type="button"
      role="tab"
      :aria-selected="model === t.value"
      class="-mb-px border-b-2 px-2.5 py-2.5 text-[13px] transition-colors"
      :class="model === t.value ? 'border-[var(--cs-ink)] font-semibold text-white' : 'border-transparent text-slate-400 hover:text-white'"
      @click="model = t.value"
    >
      {{ t.label }}<span v-if="t.count != null" class="ml-1 text-[11px] text-slate-500 tabular-nums">{{ t.count }}</span>
    </button>
  </div>
</template>
