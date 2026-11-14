<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Search, X } from 'lucide-vue-next'

/** 表格筛选条：左侧搜索（防抖 300ms），中间筛选组（插槽），右侧操作（#actions） */
const props = withDefaults(defineProps<{ placeholder?: string; search?: boolean }>(), {
  placeholder: '搜索',
  search: true,
})
const q = defineModel<string>('q', { default: '' })
const local = ref(q.value)
let timer: number | undefined
watch(local, (v) => {
  window.clearTimeout(timer)
  timer = window.setTimeout(() => (q.value = v.trim()), 300)
})
watch(q, (v) => {
  if (v !== local.value.trim()) local.value = v
})
onBeforeUnmount(() => window.clearTimeout(timer))
void props
</script>

<template>
  <div class="mb-4 flex flex-wrap items-center gap-2.5">
    <label v-if="search" class="relative w-full sm:w-72">
      <span class="sr-only">{{ placeholder }}</span>
      <Search class="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input v-model="local" class="input !rounded-full !py-2 !pr-9 !pl-10" :placeholder="placeholder" type="search" />
      <button
        v-if="local"
        type="button"
        class="absolute top-1/2 right-2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-slate-400 hover:text-white"
        aria-label="清除搜索"
        @click="local = ''"
      >
        <X class="h-3.5 w-3.5" />
      </button>
    </label>
    <slot />
    <div class="flex-1" />
    <slot name="actions" />
  </div>
</template>
