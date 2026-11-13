<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download, Loader2 } from 'lucide-vue-next'
import type { ArtifactFormat, ArtifactOut, ArtifactPreviewOut } from '@/api/types'
import { api } from '@/api/client'
import { FORMAT_LABEL, downloadFormat } from '@/lib/artifactFormats'
import { artifactKindLabel, formatBytes, formatTime, qualityLabel } from '@/lib/format'
import { renderMarkdownPlain } from '@/lib/markdown'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ artifactId: string | null }>()
const toast = useToastStore()
const panel = usePanelStore()
const fmtBusy = ref<string | null>(null)
const otherFormats = computed(() => panel.artifactFormats)

async function dlFormat(f: ArtifactFormat) {
  fmtBusy.value = f.artifact_id
  try {
    await downloadFormat({ display_name: panel.artifactName || meta.value?.display_name || '成果' }, f)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    fmtBusy.value = null
  }
}
const meta = ref<ArtifactOut | null>(null)
const preview = ref<ArtifactPreviewOut | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const downloading = ref(false)

const html = computed(() => (preview.value?.kind === 'markdown' ? renderMarkdownPlain(preview.value.content || '') : ''))
const truncated = computed(
  () => preview.value?.kind === 'table' && preview.value.total_rows != null && (preview.value.shown_rows ?? 0) < preview.value.total_rows,
)

watch(
  () => props.artifactId,
  async (id) => {
    meta.value = null
    preview.value = null
    error.value = null
    if (!id) return
    loading.value = true
    try {
      const [m, p] = await Promise.all([api.getArtifact(id), api.artifactPreview(id)])
      if (props.artifactId !== id) return
      meta.value = m
      preview.value = p
    } catch (e) {
      error.value = e instanceof Error ? e.message : '预览失败'
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

async function download() {
  if (!meta.value) return
  downloading.value = true
  try {
    await api.downloadArtifact(meta.value.artifact_id, meta.value.display_name)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    downloading.value = false
  }
}

function cell(v: unknown): string {
  if (v == null) return ''
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}
</script>

<template>
  <div class="flex h-full flex-col">
    <div v-if="meta" class="hairline flex items-start gap-3 border-b p-3">
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-medium text-white">{{ meta.display_name }}</div>
        <div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-slate-400">
          <span>{{ artifactKindLabel(meta.artifact_kind) }}</span>
          <span v-if="meta.record_qty != null">{{ meta.record_qty }} 条记录</span>
          <span>{{ formatBytes(meta.byte_qty) }}</span>
          <span>{{ qualityLabel(meta.quality_status) }}</span>
          <span>{{ formatTime(meta.created_time) }}</span>
        </div>
        <div class="mt-0.5 truncate font-mono text-[11px] text-slate-600" :title="meta.content_hash">sha256 {{ meta.content_hash.slice(0, 16) }}…</div>
      </div>
      <div v-if="otherFormats.length" class="flex flex-wrap justify-end gap-1">
        <button
          v-for="f in otherFormats"
          :key="f.artifact_id"
          class="btn-secondary btn-sm"
          :disabled="fmtBusy === f.artifact_id"
          :aria-label="`下载 ${FORMAT_LABEL[f.format]}`"
          @click="dlFormat(f)"
        >
          <Loader2 v-if="fmtBusy === f.artifact_id" class="h-3.5 w-3.5 animate-spin" />
          <Download v-else class="h-3.5 w-3.5" /> {{ FORMAT_LABEL[f.format] }}
        </button>
      </div>
      <button v-else class="btn-primary btn-sm" :disabled="downloading" @click="download">
        <Loader2 v-if="downloading" class="h-3.5 w-3.5 animate-spin" />
        <Download v-else class="h-3.5 w-3.5" /> 下载
      </button>
    </div>
    <!-- 报告（HTML）预览：沙箱 iframe，禁止脚本，与下载的排版一致 -->
    <iframe
      v-if="!loading && !error && preview?.kind === 'html'"
      class="min-h-0 w-full flex-1 border-0 bg-snow"
      sandbox=""
      referrerpolicy="no-referrer"
      title="报告预览"
      :srcdoc="preview.content || ''"
    />
    <div v-else class="min-h-0 flex-1 overflow-auto p-3">
      <div v-if="loading" class="flex items-center gap-2 text-sm text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> 加载预览…</div>
      <div v-else-if="error" class="text-sm text-rose-300">{{ error }}</div>
      <template v-else-if="preview">
        <template v-if="preview.kind === 'table'">
          <div v-if="truncated" class="mb-2 rounded-lg bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200">
            仅显示前 {{ preview.shown_rows }} 行，共 {{ preview.total_rows }} 行；完整数据请下载文件
          </div>
          <div class="overflow-auto rounded-xl border border-white/10">
            <table class="min-w-full text-left text-xs">
              <thead class="sticky top-0 bg-ink-800 shadow-[0_1px_0_var(--cs-line)]">
                <tr>
                  <th class="px-2 py-1.5 font-medium text-slate-400">#</th>
                  <th v-for="c in preview.columns || []" :key="c" class="px-2 py-1.5 font-medium whitespace-nowrap text-slate-300">{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in preview.rows || []" :key="i" class="hairline border-t align-top even:bg-white/[0.025]">
                  <td class="px-2 py-1.5 text-slate-600">{{ i + 1 }}</td>
                  <td v-for="(v, j) in r" :key="j" class="max-w-[280px] px-2 py-1.5 text-slate-200" :class="v == null || v === '' ? 'text-slate-600' : ''">
                    {{ v == null || v === '' ? '空' : cell(v) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <!-- eslint-disable-next-line vue/no-v-html -- 已净化 -->
        <div v-else-if="preview.kind === 'markdown'" class="prose-cs" v-html="html" />
        <pre v-else class="text-xs whitespace-pre-wrap text-slate-200">{{ preview.content }}</pre>
      </template>
    </div>
  </div>
</template>
