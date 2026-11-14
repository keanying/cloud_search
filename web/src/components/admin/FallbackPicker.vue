<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'
import type { ModelOut } from '@/api/types'
import { useFloating } from '@/lib/useFloating'

/** 备用模型多选：按勾选顺序作为回退顺序；下拉渲染到 body 顶层 */
const props = defineProps<{ models: ModelOut[]; exclude: string; label: string }>()
const model = defineModel<string[]>({ required: true })

const open = ref(false)
const anchor = ref<HTMLElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const { style } = useFloating(anchor, menu, open, () => 'bottom-start')

const choices = computed(() => props.models.filter((m) => m.model_profile_id !== props.exclude))
const name = (m: ModelOut) => m.display_name || m.model_name
const summary = computed(() => {
  const picked = model.value
    .map((id) => props.models.find((m) => m.model_profile_id === id))
    .filter((m): m is ModelOut => !!m && m.model_profile_id !== props.exclude)
  if (!picked.length) return '不使用'
  return picked.map((m, i) => `${i + 1}. ${name(m)}`).join('  ')
})

function toggle(id: string) {
  const i = model.value.indexOf(id)
  model.value = i >= 0 ? model.value.filter((x) => x !== id) : [...model.value, id]
}
</script>

<template>
  <div ref="anchor" class="w-full">
    <button
      type="button"
      class="input flex !py-2 items-center gap-2 text-left"
      :aria-label="label"
      :aria-expanded="open"
      :disabled="!choices.length"
      @click="open = !open"
    >
      <span class="min-w-0 flex-1 truncate" :class="summary === '不使用' ? 'text-slate-500' : ''">{{ summary }}</span>
      <ChevronDown class="h-4 w-4 shrink-0 opacity-60" />
    </button>
  </div>
  <Teleport to="body">
    <div v-if="open" ref="menu" class="popover-menu w-72" :style="style" role="listbox" :aria-label="label" aria-multiselectable="true">
      <div class="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold text-slate-400">主模型失败时按顺序尝试</div>
      <button
        v-for="m in choices"
        :key="m.model_profile_id"
        type="button"
        role="option"
        :aria-selected="model.includes(m.model_profile_id)"
        class="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm hover:bg-[var(--cs-line)]"
        @click="toggle(m.model_profile_id)"
      >
        <span
          class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold"
          :class="model.includes(m.model_profile_id) ? 'chip-active' : 'hairline'"
        >
          <template v-if="model.includes(m.model_profile_id)">{{ model.indexOf(m.model_profile_id) + 1 }}</template>
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate text-white">{{ name(m) }}</span>
          <span class="block truncate text-[11px] text-slate-500">{{ m.provider_name }}</span>
        </span>
        <Check v-if="model.includes(m.model_profile_id)" class="h-4 w-4 text-emerald-300" />
      </button>
      <div v-if="!choices.length" class="px-3 py-3 text-xs text-slate-400">没有其他可用模型</div>
    </div>
  </Teleport>
</template>
