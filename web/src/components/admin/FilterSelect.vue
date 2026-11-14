<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, ChevronDown, X } from 'lucide-vue-next'
import { useFloating } from '@/lib/useFloating'

/** 下拉筛选（单选）：按钮显示「标签：当前值」，选中后可一键清除 */
const props = withDefaults(defineProps<{ label: string; options: { value: string; label: string; dot?: string }[]; allLabel?: string }>(), {
  allLabel: '全部',
})
const model = defineModel<string>({ default: '' })
const open = ref(false)
const anchor = ref<HTMLElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const { style } = useFloating(anchor, menu, open, () => 'bottom-start')
const current = computed(() => props.options.find((o) => o.value === model.value))
function pick(v: string) {
  model.value = v
  open.value = false
}
</script>

<template>
  <div ref="anchor" class="inline-flex">
    <button
      type="button"
      class="fs-btn"
      :class="current ? 'fs-on' : ''"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="open = !open"
    >
      <span class="text-slate-400">{{ label }}</span>
      <template v-if="current">
        <span class="text-slate-500">:</span>
        <span v-if="current.dot" class="h-1.5 w-1.5 rounded-full" :style="{ background: current.dot }" />
        <span class="font-semibold text-white">{{ current.label }}</span>
      </template>
      <ChevronDown v-if="!current" class="h-3.5 w-3.5 opacity-60" />
      <span
        v-else
        role="button"
        tabindex="0"
        class="-mr-1 ml-0.5 inline-flex h-4 w-4 items-center justify-center rounded text-slate-400 hover:bg-[var(--cs-line)] hover:text-white"
        :aria-label="`清除${label}筛选`"
        @click.stop="model = ''"
        @keydown.enter.stop="model = ''"
      >
        <X class="h-3 w-3" />
      </span>
    </button>
  </div>
  <Teleport to="body">
    <div v-if="open" ref="menu" class="popover-menu min-w-44" :style="style" role="listbox" :aria-label="label">
      <button type="button" role="option" :aria-selected="!model" class="fs-opt" @click="pick('')">
        <span class="flex-1">{{ allLabel }}</span>
        <Check v-if="!model" class="h-3.5 w-3.5" />
      </button>
      <button
        v-for="o in options"
        :key="o.value"
        type="button"
        role="option"
        :aria-selected="model === o.value"
        class="fs-opt"
        @click="pick(o.value)"
      >
        <span v-if="o.dot" class="h-1.5 w-1.5 shrink-0 rounded-full" :style="{ background: o.dot }" />
        <span class="flex-1">{{ o.label }}</span>
        <Check v-if="model === o.value" class="h-3.5 w-3.5" />
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.fs-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  height: 32px;
  padding: 0 0.7rem;
  border-radius: 8px;
  border: 1px dashed var(--cs-line-strong);
  background: var(--cs-surface-solid);
  font-size: 12px;
  white-space: nowrap;
}
.fs-btn:hover {
  border-color: var(--color-slate-400);
}
.fs-on {
  border-style: solid;
}
.fs-opt {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.5rem;
  border-radius: 8px;
  padding: 0.4rem 0.6rem;
  font-size: 13px;
  text-align: left;
  color: var(--color-slate-100);
}
.fs-opt:hover {
  background: var(--cs-line);
}
</style>
