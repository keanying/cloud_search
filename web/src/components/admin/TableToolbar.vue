<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Columns3, RefreshCw, Rows3, Rows4, Search, X } from 'lucide-vue-next'
import type { Column } from '@/components/common/DataTable.vue'
import { useFloating } from '@/lib/useFloating'

/**
 * 表格工具条：左侧搜索（防抖）+ 筛选（默认插槽）；右侧 刷新 / 密度 / 列设置 + #actions。
 * 列设置只在传入 toggleable 时显示；隐藏列通过 v-model:hidden 绑定。
 */
const props = withDefaults(
  defineProps<{ placeholder?: string; search?: boolean; loading?: boolean; toggleable?: Column[]; refreshable?: boolean }>(),
  { placeholder: '搜索', search: true, loading: false, toggleable: () => [], refreshable: true },
)
const emit = defineEmits<{ refresh: [] }>()
const q = defineModel<string>('q', { default: '' })
const hidden = defineModel<string[]>('hidden', { default: () => [] })
const density = defineModel<'default' | 'compact'>('density', { default: 'default' })

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

const colOpen = ref(false)
const colAnchor = ref<HTMLElement | null>(null)
const colMenu = ref<HTMLElement | null>(null)
const { style } = useFloating(colAnchor, colMenu, colOpen, () => 'bottom-end')
function toggleCol(k: string) {
  hidden.value = hidden.value.includes(k) ? hidden.value.filter((x) => x !== k) : [...hidden.value, k]
}
void props
</script>

<template>
  <div class="mb-3 flex flex-wrap items-center gap-2">
    <label v-if="search" class="relative w-full sm:w-64">
      <span class="sr-only">{{ placeholder }}</span>
      <Search class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
      <input v-model="local" class="input !py-1.5 !pr-8 !pl-8" :placeholder="placeholder" type="search" />
      <button
        v-if="local"
        type="button"
        class="absolute top-1/2 right-1.5 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded text-slate-400 hover:text-white"
        aria-label="清除搜索"
        @click="local = ''"
      >
        <X class="h-3 w-3" />
      </button>
    </label>
    <slot />
    <div class="flex-1" />
    <slot name="actions" />
    <button v-if="refreshable" type="button" class="icon-btn" title="刷新" aria-label="刷新" :disabled="loading" @click="emit('refresh')">
      <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
    </button>
    <button
      type="button"
      class="icon-btn"
      :title="density === 'compact' ? '默认密度' : '紧凑密度'"
      :aria-label="density === 'compact' ? '切换为默认密度' : '切换为紧凑密度'"
      @click="density = density === 'compact' ? 'default' : 'compact'"
    >
      <Rows3 v-if="density === 'compact'" class="h-4 w-4" />
      <Rows4 v-else class="h-4 w-4" />
    </button>
    <div v-if="toggleable.length" ref="colAnchor" class="inline-flex">
      <button type="button" class="icon-btn" title="显示的列" aria-label="设置显示的列" :aria-expanded="colOpen" @click="colOpen = !colOpen">
        <Columns3 class="h-4 w-4" />
      </button>
    </div>
    <Teleport to="body">
      <div v-if="colOpen" ref="colMenu" class="popover-menu w-48" :style="style" role="menu" aria-label="显示的列">
        <div class="px-2 pt-1 pb-1.5 text-[11px] font-semibold text-slate-400">显示的列</div>
        <label
          v-for="c in toggleable"
          :key="c.key"
          class="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] hover:bg-[var(--cs-line)]"
        >
          <input type="checkbox" class="accent-[var(--cs-ink)]" :checked="!hidden.includes(c.key)" @change="toggleCol(c.key)" />
          {{ c.title }}
        </label>
      </div>
    </Teleport>
  </div>
</template>
