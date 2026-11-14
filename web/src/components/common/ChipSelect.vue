<script setup lang="ts">
/** 单选筛选胶囊：「全部」+ 选项；再次点击当前项回到全部 */
withDefaults(defineProps<{ options: { value: string; label: string; dot?: string }[]; label: string; allLabel?: string }>(), {
  allLabel: '全部',
})
const model = defineModel<string>({ default: '' })
</script>

<template>
  <div class="flex flex-wrap items-center gap-1.5" role="radiogroup" :aria-label="label">
    <span class="mr-0.5 text-xs font-semibold text-slate-400">{{ label }}</span>
    <button type="button" role="radio" :aria-checked="!model" class="chip !px-2.5 !py-1 !text-xs" :class="!model ? 'chip-active' : ''" @click="model = ''">
      {{ allLabel }}
    </button>
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      :aria-checked="model === o.value"
      class="chip !px-2.5 !py-1 !text-xs"
      :class="model === o.value ? 'chip-active' : ''"
      @click="model = model === o.value ? '' : o.value"
    >
      <span v-if="o.dot" class="h-2 w-2 rounded-full" :style="{ background: o.dot }" />
      {{ o.label }}
    </button>
  </div>
</template>
