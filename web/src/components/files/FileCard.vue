<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, Loader2 } from 'lucide-vue-next'
import { formatSize, middleTruncate, statusLine } from '@/lib/fileTypes'
import FileTypeIcon from './FileTypeIcon.vue'

/** 已发送的文件（用户消息里、对话文件列表）：图标、名称、大小、实时解析状态；点击预览 */
const props = defineProps<{
  name: string
  ext: string
  byteQty: number
  status: string
  pages?: number | null
  parser?: string | null
  detail?: string | null
  error?: string | null
  compact?: boolean
}>()
defineEmits<{ open: [] }>()
const busy = computed(() => props.status === 'queued' || props.status === 'parsing')
const parserName = computed(() => props.parser ?? (props.detail?.includes('MinerU') ? 'mineru' : props.detail ? 'builtin' : null))
const line = computed(() => statusLine(props.status, { pages: props.pages, parser: parserName.value }))
</script>

<template>
  <button
    type="button"
    class="file-card flex w-full items-center gap-2.5 rounded-2xl border text-left transition hover:-translate-y-px hover:shadow-sm"
    :class="[compact ? 'p-2' : 'p-2.5', status === 'failed' ? 'border-rose-300/60' : 'hairline']"
    :title="[name, detail, error].filter(Boolean).join('\n')"
    @click="$emit('open')"
  >
    <FileTypeIcon :ext="ext" :size="compact ? 'sm' : 'md'" />
    <span class="min-w-0 flex-1">
      <span class="block truncate text-[13px] font-semibold text-white">{{ middleTruncate(name, compact ? 26 : 32) }}</span>
      <span class="flex items-center gap-1 text-[11.5px]" :class="status === 'failed' ? 'text-rose-300' : status === 'parsed' ? 'text-brand-300' : 'text-slate-400'">
        <Loader2 v-if="busy" class="h-3 w-3 animate-spin" />
        <AlertCircle v-else-if="status === 'failed'" class="h-3 w-3" />
        <span class="truncate">{{ line }}</span>
        <span class="shrink-0 text-slate-500">· {{ formatSize(byteQty) }}</span>
      </span>
    </span>
  </button>
</template>

<style scoped>
.file-card {
  background-color: var(--cs-surface-solid);
}
</style>
