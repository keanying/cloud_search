<script setup lang="ts">
defineProps<{ title: string; desc?: string }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-1 px-4 py-6 text-center">
    <div class="text-sm text-slate-300">{{ title }}</div>
    <div v-if="desc" class="text-xs text-slate-500">{{ desc }}</div>
    <slot />
  </div>
</template>
