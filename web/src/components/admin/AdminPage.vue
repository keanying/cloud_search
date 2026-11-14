<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { findAdminItem } from '@/lib/adminNav'

/**
 * 管理后台页面骨架：紧凑页头（22px 标题 + 13px 说明 + 右侧操作）、可选标签行、内容。
 * wide：不限制最大宽度（主从布局等）。
 */
const props = defineProps<{ title?: string; desc?: string; wide?: boolean }>()
const route = useRoute()
const found = computed(() => findAdminItem(route.name))
const title = computed(() => props.title ?? found.value?.label ?? '管理后台')
const desc = computed(() => props.desc ?? found.value?.desc ?? '')
</script>

<template>
  <div class="mx-auto w-full px-4 pt-6 pb-16 sm:px-6 lg:px-8" :class="wide ? 'max-w-none' : 'max-w-[1600px]'">
    <header class="mb-5 flex flex-wrap items-start gap-x-6 gap-y-3">
      <div class="min-w-[min(100%,20rem)] flex-1">
        <h1 class="text-[22px] leading-8 font-bold tracking-tight text-white">{{ title }}</h1>
        <p v-if="desc" class="mt-0.5 max-w-3xl text-[13px] leading-5 text-slate-400">{{ desc }}</p>
      </div>
      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2"><slot name="actions" /></div>
    </header>
    <slot name="tabs" />
    <slot />
  </div>
</template>
