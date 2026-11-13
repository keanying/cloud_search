<script setup lang="ts">
import { ref } from 'vue'
import { Download, Eye, FileSpreadsheet, FileText, Loader2 } from 'lucide-vue-next'
import type { ArtifactPart } from '@/api/types'
import { api } from '@/api/client'
import { artifactKindLabel, formatBytes, qualityLabel } from '@/lib/format'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ part: ArtifactPart }>()
const panel = usePanelStore()
const toast = useToastStore()
const downloading = ref(false)

const isTable = props.part.artifact_kind === 'dataset' || /csv|sheet|excel/.test(props.part.mime_name)

async function download() {
  downloading.value = true
  try {
    await api.downloadArtifact(props.part.artifact_id, props.part.display_name)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <div class="glass flex items-center gap-3 p-3">
    <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-500/20">
      <FileSpreadsheet v-if="isTable" class="h-5 w-5 text-brand-300" />
      <FileText v-else class="h-5 w-5 text-brand-300" />
    </div>
    <div class="min-w-0 flex-1">
      <div class="truncate text-sm font-medium text-white">{{ part.display_name }}</div>
      <div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-slate-400">
        <span>{{ artifactKindLabel(part.artifact_kind) }}</span>
        <span v-if="part.record_qty != null">{{ part.record_qty }} 条记录</span>
        <span>{{ formatBytes(part.byte_qty) }}</span>
        <span v-if="part.quality_status">{{ qualityLabel(part.quality_status) }}</span>
      </div>
    </div>
    <button class="btn-secondary btn-sm" @click="panel.openArtifact(part.artifact_id, part.task_id)">
      <Eye class="h-3.5 w-3.5" /> 预览
    </button>
    <button class="btn-primary btn-sm" :disabled="downloading" @click="download">
      <Loader2 v-if="downloading" class="h-3.5 w-3.5 animate-spin" />
      <Download v-else class="h-3.5 w-3.5" /> 下载
    </button>
  </div>
</template>
