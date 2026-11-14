<script setup lang="ts" generic="V extends string | number">
/** 分段选择（7天 / 14天 / 30天 等） */
defineProps<{ options: { value: V; label: string }[]; label?: string; small?: boolean }>()
const model = defineModel<V>({ required: true })
</script>

<template>
  <div class="sunken hairline inline-flex gap-0.5 rounded-full border p-1" role="radiogroup" :aria-label="label">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      :aria-checked="model === o.value"
      class="rounded-full font-semibold whitespace-nowrap transition-colors"
      :class="[small ? 'px-3 py-1 text-xs' : 'px-4 py-1.5 text-sm', model === o.value ? 'chip-active' : 'text-slate-400 hover:text-white']"
      @click="model = o.value"
    >
      {{ o.label }}
    </button>
  </div>
</template>
