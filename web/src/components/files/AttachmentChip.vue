<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, Loader2, RotateCw, X } from 'lucide-vue-next'
import type { Attachment } from '@/lib/useAttachments'
import { formatSize, middleTruncate, statusLine } from '@/lib/fileTypes'
import FileTypeIcon from './FileTypeIcon.vue'

/** 输入框上方的附件：上传进度 → 排队/解析中 → 已解析 / 解析失败（可重试） */
const props = defineProps<{ att: Attachment }>()
const emit = defineEmits<{ remove: []; retry: []; open: [] }>()

const busy = computed(() => ['uploading', 'queued', 'parsing'].includes(props.att.status))
const bad = computed(() => props.att.status === 'failed' || props.att.status === 'upload_failed')
const line = computed(() =>
  statusLine(props.att.status, {
    pages: props.att.file?.page_qty,
    parser: props.att.file?.parser,
    progress: props.att.progress,
    error: props.att.error,
  }),
)
const tip = computed(() => {
  const parts = [props.att.name, formatSize(props.att.size)]
  if (props.att.file?.parse_detail) parts.push(props.att.file.parse_detail)
  if (props.att.error) parts.push(props.att.error)
  return parts.join('\n')
})
</script>

<template>
  <div
    class="chip-card group relative flex w-[264px] max-w-full items-center gap-2.5 overflow-hidden rounded-2xl border py-2 pr-8 pl-2"
    :class="bad ? 'border-rose-300/60' : 'hairline'"
    :title="tip"
  >
    <button
      type="button"
      class="flex min-w-0 flex-1 items-center gap-2.5 text-left"
      :disabled="!att.file"
      :aria-label="`查看 ${att.name}`"
      @click="emit('open')"
    >
      <FileTypeIcon :ext="att.ext" size="sm" />
      <span class="min-w-0 flex-1">
        <span class="block truncate text-[13px] font-semibold text-white">{{ middleTruncate(att.name, 24) }}</span>
        <span class="flex items-center gap-1 text-[11.5px]" :class="bad ? 'text-rose-300' : att.status === 'parsed' ? 'text-brand-300' : 'text-slate-400'">
          <Loader2 v-if="busy && att.status !== 'uploading'" class="h-3 w-3 animate-spin" />
          <AlertCircle v-else-if="bad" class="h-3 w-3" />
          <span class="truncate">{{ line }}</span>
          <span v-if="!['upload_failed', 'parsed'].includes(att.status)" class="shrink-0 text-slate-500">· {{ formatSize(att.size) }}</span>
        </span>
      </span>
    </button>
    <button
      v-if="att.status === 'failed' && att.file"
      type="button"
      class="shrink-0 rounded-full p-1 text-slate-400 hover:bg-[var(--cs-line)] hover:text-white"
      title="重新解析"
      aria-label="重新解析"
      @click="emit('retry')"
    >
      <RotateCw class="h-3.5 w-3.5" />
    </button>
    <button
      type="button"
      class="absolute top-1.5 right-1.5 rounded-full p-1 text-slate-400 opacity-70 hover:bg-[var(--cs-line)] hover:text-white group-hover:opacity-100"
      :aria-label="`移除 ${att.name}`"
      title="移除"
      @click="emit('remove')"
    >
      <X class="h-3.5 w-3.5" />
    </button>
    <div v-if="att.status === 'uploading'" class="absolute inset-x-0 bottom-0 h-[3px] bg-[var(--cs-line)]">
      <div class="h-full bg-brand-400 transition-[width]" :style="{ width: `${att.progress}%` }" />
    </div>
  </div>
</template>

<style scoped>
.chip-card {
  background-color: var(--cs-surface-sunken);
}
</style>
