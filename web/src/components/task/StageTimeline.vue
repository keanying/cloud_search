<script setup lang="ts">
import { Check, X } from 'lucide-vue-next'
import type { StageStatus } from '@/api/types'

/** 阶段时间线：圆点 + 虚线连接 */
defineProps<{ stages: { key: string; label: string; status: StageStatus }[]; dense?: boolean }>()
</script>

<template>
  <ol class="relative">
    <li v-for="(s, i) in stages" :key="s.key" class="relative flex gap-3" :class="i < stages.length - 1 ? (dense ? 'pb-2.5' : 'pb-3.5') : ''">
      <span
        v-if="i < stages.length - 1"
        class="dotted-line absolute top-6 bottom-0 left-[11px] text-slate-400"
        aria-hidden="true"
      />
      <span
        class="relative z-[1] mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
        :class="{
          'bg-[var(--cs-ink)] text-[var(--cs-on-ink)]': s.status === 'done',
          'cs-ping accent-dot text-[var(--accent-dot,var(--color-brand-500))] ring-4 ring-white/40': s.status === 'running',
          'border-2 border-dashed border-slate-500 bg-transparent': s.status === 'pending',
          'card-peach accent-ink': s.status === 'failed',
          'border border-slate-600 text-slate-500': s.status === 'skipped',
        }"
        aria-hidden="true"
      >
        <Check v-if="s.status === 'done'" class="h-3.5 w-3.5" stroke-width="3" />
        <X v-else-if="s.status === 'failed'" class="h-3.5 w-3.5" stroke-width="3" />
        <span v-else-if="s.status === 'running'" class="h-2 w-2 rounded-full bg-[var(--cs-surface-solid)]" />
        <span v-else-if="s.status === 'skipped'">–</span>
      </span>
      <span class="min-w-0 pt-0.5 text-sm leading-5" :class="s.status === 'pending' || s.status === 'skipped' ? 'text-slate-500' : 'font-medium text-slate-100'">
        {{ s.label }}
        <span v-if="s.status === 'running'" class="ml-1 text-xs font-semibold accent-ink">进行中</span>
        <span v-else-if="s.status === 'skipped'" class="ml-1 text-xs">（跳过）</span>
        <span v-else-if="s.status === 'failed'" class="ml-1 text-xs text-rose-300">失败</span>
      </span>
    </li>
  </ol>
</template>
