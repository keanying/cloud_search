<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ADMIN_NAV } from '@/lib/adminNav'

/** 管理后台页面骨架：面包屑 + 标题/说明 + 右侧操作；内容区全宽（最大 1680px） */
const props = defineProps<{ title?: string; desc?: string }>()
const route = useRoute()
const found = computed(() => {
  for (const g of ADMIN_NAV) {
    const it = g.items.find((i) => i.name === route.name)
    if (it) return { group: g.group, item: it }
  }
  return null
})
const title = computed(() => props.title ?? found.value?.item.label ?? '管理后台')
const desc = computed(() => props.desc ?? found.value?.item.desc ?? '')
</script>

<template>
  <div class="mx-auto w-full max-w-[1680px] px-4 pt-5 pb-16 sm:px-6 lg:px-10 lg:pt-8">
    <header class="mb-6 flex flex-wrap items-end gap-x-6 gap-y-4">
      <div class="min-w-0 flex-1">
        <div class="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-400">
          <span>管理后台</span>
          <template v-if="found?.group"><span aria-hidden="true">/</span><span>{{ found.group }}</span></template>
        </div>
        <h1 class="flex items-center gap-3 text-[28px] leading-9 font-bold tracking-tight text-white lg:text-[34px] lg:leading-[42px]">
          <component :is="found.item.icon" v-if="found" class="hidden h-7 w-7 shrink-0 opacity-80 sm:block" />
          {{ title }}
        </h1>
        <p v-if="desc" class="mt-1.5 max-w-3xl text-[15px] text-slate-400">{{ desc }}</p>
      </div>
      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2"><slot name="actions" /></div>
    </header>
    <slot />
  </div>
</template>
