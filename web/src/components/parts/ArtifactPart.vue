<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, Eye, FileBarChart, FileSpreadsheet, FileText, Loader2 } from 'lucide-vue-next'
import type { ArtifactFormat, ArtifactPart, ArtifactPreviewOut } from '@/api/types'
import DataPreviewTable from '@/components/common/DataPreviewTable.vue'
import { api } from '@/api/client'
import { artifactKindLabel, formatBytes, qualityLabel } from '@/lib/format'
import { FORMAT_LABEL, FORMAT_TONE, downloadFormat, partFormats, previewArtifactId } from '@/lib/artifactFormats'
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

// 数据成果：卡片内直接显示前几行（完整表格点“预览”在右侧打开）
const table = ref<ArtifactPreviewOut | null>(null)
onMounted(async () => {
  if (!isTable.value) return
  try {
    const p = await api.artifactPreview(previewArtifactId(props.part))
    if (p.kind === 'table') table.value = p
  } catch {
    /* 预览失败不影响下载 */
  }
})

function preview() {
  panel.openArtifact(previewArtifactId(props.part), props.part.task_id, formats.value, props.part.display_name)
}
</script>

<template>
  <div class="card-sky holo-card p-5">
    <div class="flex items-center gap-3">
      <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--cs-surface-solid)]">
        <FileSpreadsheet v-if="isTable" class="h-6 w-6 accent-ink" />
        <FileBarChart v-else-if="isReport" class="h-6 w-6 accent-ink" />
        <FileText v-else class="h-6 w-6 accent-ink" />
      </div>
      <div class="min-w-0 flex-1">
        <div class="text-xs font-bold tracking-wide accent-ink">📦 {{ artifactKindLabel(part.artifact_kind) }}已生成</div>
        <div class="truncate text-[15px] font-bold tracking-tight text-white">{{ title }}</div>
        <div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-slate-300">
          <span v-if="part.record_qty != null">{{ part.record_qty }} 条记录</span>
          <span v-if="!formats.length || formats.length === 1">{{ formatBytes(part.byte_qty) }}</span>
          <span v-if="part.quality_status">{{ qualityLabel(part.quality_status) }}</span>
        </div>
      </div>
      <button class="btn-primary btn-sm shrink-0" @click="preview"><Eye class="h-3.5 w-3.5" /> 预览</button>
    </div>
    <div v-if="table && (table.rows || []).length" class="mt-4">
      <DataPreviewTable compact :columns="table.columns || []" :rows="table.rows || []" :task-id="part.task_id" :max-rows="5" :max-cols="6" />
      <button type="button" class="mt-1.5 text-xs font-semibold accent-ink hover:underline" @click="preview">
        查看全部 {{ table.total_rows ?? table.rows?.length }} 行 · {{ (table.columns || []).length }} 列 →
      </button>
    </div>
    <div class="mt-4 flex flex-wrap items-center gap-1.5">
      <template v-if="formats.length">
        <span class="mr-1 text-xs font-semibold text-slate-300">下载</span>
        <button
          v-for="f in formats"
          :key="f.artifact_id"
          class="pill !px-3 !py-1.5 bg-[var(--cs-surface-solid)] text-slate-100 transition hover:-translate-y-px hover:shadow-sm"
          :disabled="busy === f.artifact_id"
          :title="`下载 ${FORMAT_LABEL[f.format]}（${formatBytes(f.byte_qty)}）`"
          @click="dl(f)"
        >
          <Loader2 v-if="busy === f.artifact_id" class="h-3.5 w-3.5 animate-spin" />
          <span v-else class="h-2.5 w-2.5 rounded-full" :style="{ background: `var(--pastel-${FORMAT_TONE[f.format]}-dot)` }" />
          {{ FORMAT_LABEL[f.format] }}
          <Download class="h-3 w-3 opacity-60" />
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
