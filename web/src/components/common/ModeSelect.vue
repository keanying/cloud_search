<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import { MODE_OPTIONS } from '@/lib/format'

const model = defineModel<ModeSelection>({ required: true })
const props = defineProps<{ placement?: 'top' | 'bottom' }>()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const current = computed(() => MODE_OPTIONS.find((m) => m.value === model.value) ?? MODE_OPTIONS[0])

function pick(v: ModeSelection) {
  model.value = v
  open.value = false
}
function onDoc(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('mousedown', onDoc))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDoc))
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      class="inline-flex items-center gap-1 rounded-xl border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-slate-100 hover:bg-white/10"
      :aria-expanded="open"
      aria-haspopup="listbox"
      aria-label="选择执行模式"
      @click="open = !open"
      @keydown.escape="open = false"
    >
      {{ current.label }}
      <ChevronDown class="h-4 w-4 text-slate-400" />
    </button>
    <ul
      v-if="open"
      role="listbox"
      class="glass-strong absolute z-40 w-64 p-1"
      :class="props.placement === 'bottom' ? 'top-full mt-2 left-0' : 'bottom-full mb-2 right-0'"
    >
      <li v-for="m in MODE_OPTIONS" :key="m.value">
        <button
          type="button"
          role="option"
          :aria-selected="m.value === model"
          class="flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left hover:bg-white/10"
          @click="pick(m.value)"
        >
          <Check class="mt-0.5 h-4 w-4 shrink-0" :class="m.value === model ? 'text-brand-300' : 'opacity-0'" />
          <span>
            <span class="block text-sm text-white">{{ m.label }}</span>
            <span class="block text-xs text-slate-400">{{ m.desc }}</span>
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>
