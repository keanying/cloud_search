<script setup lang="ts">
import { computed, ref } from 'vue'
import { Library } from 'lucide-vue-next'
import type { SourcePart } from '@/api/types'
import { hostOf } from '@/lib/format'
import { usePanelStore } from '@/stores/panel'

const props = defineProps<{ part: SourcePart }>()
const panel = usePanelStore()
const expanded = ref(false)
const shown = computed(() => (expanded.value ? props.part.sources : props.part.sources.slice(0, 4)))
</script>

<template>
  <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
    <div class="mb-2 flex items-center gap-2 text-xs text-slate-400">
      <Library class="h-3.5 w-3.5" /> 引用来源（{{ part.sources.length }}）
      <div class="flex-1" />
      <button class="text-brand-300 hover:text-white" @click="panel.openSources(part.task_id)">全部来源</button>
    </div>
    <ul class="grid gap-1.5 sm:grid-cols-2">
      <li v-for="s in shown" :key="s.source_revision_id">
        <button
          class="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-white/5"
          @click="panel.openSources(part.task_id, s.n)"
        >
          <span class="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-md bg-brand-500/25 px-1 text-[11px] font-semibold text-brand-300">
            {{ s.n }}
          </span>
          <span class="min-w-0">
            <span class="block truncate text-sm text-slate-100">{{ s.title || s.url }}</span>
            <span class="block truncate text-xs text-slate-500">{{ s.site_name || hostOf(s.url) }}</span>
          </span>
        </button>
      </li>
    </ul>
    <button v-if="part.sources.length > 4" class="mt-1 text-xs text-slate-400 hover:text-white" @click="expanded = !expanded">
      {{ expanded ? '收起' : `展开其余 ${part.sources.length - 4} 个` }}
    </button>
  </div>
</template>
