<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, Eye, FileBarChart, FileSpreadsheet, FileText, Loader2 } from 'lucide-vue-next'
import type { ArtifactFormat, ArtifactPart } from '@/api/types'
import { api } from '@/api/client'
import { artifactKindLabel, formatBytes, qualityLabel } from '@/lib/format'
import { FORMAT_LABEL, downloadFormat, partFormats, previewArtifactId } from '@/lib/artifactFormats'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ part: ArtifactPart }>()
const panel = usePanelStore()
const toast = useToastStore()
const busy = ref<string | null>(null)

const formats = computed(() => partFormats(props.part))
const isTable = computed(() => props.part.artifact_kind === 'dataset' || /csv|sheet|excel/.test(props.part.mime_name))
const isReport = computed(() => props.part.artifact_kind === 'report' || formats.value.some((f) => f.format === 'docx'))
const title = computed(() => props.part.display_name.replace(/\.[A-Za-z0-9]{1,5}$/, ''))

async function dl(f: ArtifactFormat) {
  busy.value = f.artifact_id
  try {
    await downloadFormat(props.part, f)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    busy.value = null
  }
}

/** 旧数据（无可识别格式）：按原文件名下载 */
async function dlOriginal() {
  busy.value = props.part.artifact_id
  try {
    await api.downloadArtifact(props.part.artifact_id, props.part.display_name)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    busy.value = null
  }
}

function preview() {
  panel.openArtifact(previewArtifactId(props.part), props.part.task_id, formats.value, props.part.display_name)
}
</script>

<template>
  <div class="surface p-3.5">
    <div class="flex items-center gap-3">
      <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" :class="isTable ? 'bg-emerald-500/12' : 'bg-brand-500/12'">
        <FileSpreadsheet v-if="isTable" class="h-5 w-5 text-emerald-500" />
        <FileBarChart v-else-if="isReport" class="h-5 w-5 text-brand-500" />
        <FileText v-else class="h-5 w-5 text-brand-500" />
      </div>
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-semibold text-white">{{ title }}</div>
        <div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-slate-400">
          <span>{{ artifactKindLabel(part.artifact_kind) }}</span>
          <span v-if="part.record_qty != null">{{ part.record_qty }} 条记录</span>
          <span v-if="!formats.length || formats.length === 1">{{ formatBytes(part.byte_qty) }}</span>
          <span v-if="part.quality_status">{{ qualityLabel(part.quality_status) }}</span>
        </div>
      </div>
      <button class="btn-secondary btn-sm shrink-0" @click="preview"><Eye class="h-3.5 w-3.5" /> 预览</button>
    </div>
    <div class="mt-3 flex flex-wrap gap-1.5">
      <template v-if="formats.length">
        <button
          v-for="f in formats"
          :key="f.artifact_id"
          class="btn-secondary btn-sm"
          :disabled="busy === f.artifact_id"
          :title="`下载 ${FORMAT_LABEL[f.format]}（${formatBytes(f.byte_qty)}）`"
          @click="dl(f)"
        >
          <Loader2 v-if="busy === f.artifact_id" class="h-3.5 w-3.5 animate-spin" />
          <Download v-else class="h-3.5 w-3.5" /> {{ FORMAT_LABEL[f.format] }}
        </button>
      </template>
      <button
        v-else
        class="btn-primary btn-sm"
        :disabled="!!busy"
        @click="dlOriginal"
      >
        <Download class="h-3.5 w-3.5" /> 下载
      </button>
    </div>
  </div>
</template>
