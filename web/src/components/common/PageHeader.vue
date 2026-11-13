<script setup lang="ts">
import { useRouter, type RouteLocationRaw } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'

/** 二级页面统一页头：「← 返回」+ 标题 + 说明；右侧插槽放操作 */
const props = defineProps<{ title: string; desc?: string; parent?: RouteLocationRaw; emoji?: string }>()
const router = useRouter()

function back() {
  // vue-router 在 history.state.back 中记录应用内上一页
  const st = window.history.state as { back?: string | null } | null
  if (st?.back) router.back()
  else router.push(props.parent ?? '/')
}
</script>

<template>
  <header class="mb-6">
    <button class="btn-secondary btn-sm !py-2 !pl-2.5" aria-label="返回上一页" @click="back">
      <ArrowLeft class="h-4 w-4" /> 返回
    </button>
    <div class="mt-4 flex flex-wrap items-end gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="flex items-center gap-2.5 text-[28px] leading-9 font-bold tracking-tight text-white sm:text-[32px] sm:leading-10">
          <span v-if="emoji" aria-hidden="true">{{ emoji }}</span>{{ title }}
        </h1>
        <p v-if="desc" class="mt-1.5 max-w-2xl text-[15px] text-slate-400">{{ desc }}</p>
      </div>
      <slot />
    </div>
  </header>
</template>
