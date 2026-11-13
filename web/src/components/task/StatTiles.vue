<script setup lang="ts">
/** 统计格：大号数字 + 小标签 */
defineProps<{ items: { label: string; value: number | string; tone?: 'mint' | 'lilac' | 'butter' | 'sky' | 'peach' | 'white' }[] }>()
</script>

<template>
  <div class="grid gap-2" :style="{ gridTemplateColumns: `repeat(${Math.min(items.length, 4)}, minmax(0, 1fr))` }">
    <div
      v-for="it in items"
      :key="it.label"
      class="flex min-w-0 flex-col rounded-2xl px-3 py-2.5"
      :class="it.tone && it.tone !== 'white' ? `card-${it.tone}` : 'tile'"
    >
      <span class="text-[26px] leading-8 font-bold tracking-tight text-white tabular-nums">{{ it.value }}</span>
      <span class="truncate text-xs font-medium text-slate-300">{{ it.label }}</span>
    </div>
  </div>
</template>
