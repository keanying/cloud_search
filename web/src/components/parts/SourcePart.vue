<script setup lang="ts">
import { computed, ref } from 'vue'
import { FileText, Library } from 'lucide-vue-next'
import type { SourcePart } from '@/api/types'
import { credibilityTone, hostOf } from '@/lib/format'
import { fileIdFromUrl } from '@/lib/fileTypes'
import type { SourceBrief } from '@/api/types'
import { usePanelStore } from '@/stores/panel'

const props = defineProps<{ part: SourcePart }>()
const panel = usePanelStore()
const expanded = ref(false)
const shown = computed(() => (expanded.value ? props.part.sources : props.part.sources.slice(0, 4)))
/** 可信来源（官方/学术/权威媒体）数量，给用户一个整体判断 */
const trusted = computed(
  () => props.part.sources.filter((s) => ['official', 'academic', 'media'].includes(s.credibility ?? '')).length,
)
function fileIdOf(s: SourceBrief): string | null {
  return s.access_method === 'user_file' || s.credibility === 'user_file' ? s.file_id || fileIdFromUrl(s.url) : null
}
const fileCount = computed(() => props.part.sources.filter((s) => fileIdOf(s)).length)
function open(s: SourceBrief) {
  const fid = fileIdOf(s)
  if (fid) panel.openFile(fid)
  else panel.openSources(props.part.task_id, s.n)
}
function badgeStyle(c?: string) {
  const t = credibilityTone(c)
  return t ? { background: `var(--pastel-${t})`, color: `var(--pastel-${t}-ink)` } : undefined
}
</script>

<template>
  <div class="surface px-4 py-3.5">
    <div class="mb-2 flex items-center gap-2 text-xs muted">
      <Library class="h-3.5 w-3.5" />
      <span class="font-semibold">引用来源 {{ part.sources.length }}</span>
      <span v-if="fileCount" class="hidden sm:inline">· 你上传的文件 {{ fileCount }} 处</span>
      <span v-if="trusted" class="hidden sm:inline">· 其中官方/学术/权威媒体 {{ trusted }} 个</span>
      <div class="flex-1" />
      <button class="font-semibold accent-ink hover:underline" @click="panel.openSources(part.task_id)">全部来源</button>
    </div>
    <ul class="grid gap-1 sm:grid-cols-2">
      <li v-for="s in shown" :key="s.source_revision_id">
        <button
          class="flex w-full items-start gap-2.5 rounded-xl px-2 py-2 text-left transition hover:bg-[var(--cs-line)]"
          :title="fileIdOf(s) ? '查看文件' : '查看来源详情'"
          @click="open(s)"
        >
          <span class="cite-chip !m-0 !mt-1 !align-middle">{{ s.n }}</span>
          <FileText v-if="fileIdOf(s)" class="mt-0.5 h-4 w-4 shrink-0 text-brand-300" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium text-white">{{ s.title || s.url }}</span>
            <span class="mt-0.5 flex items-center gap-1.5 text-xs muted">
              <span v-if="!fileIdOf(s)" class="truncate">{{ s.site_name || hostOf(s.url) }}</span>
              <span v-if="s.credibility_label && s.credibility !== 'unknown'" class="cred" :style="badgeStyle(s.credibility)">
                {{ s.credibility_label }}
              </span>
              <span v-if="s.publish_time_text" class="shrink-0">· {{ s.publish_time_text }}</span>
            </span>
          </span>
        </button>
      </li>
    </ul>
    <button v-if="part.sources.length > 4" class="mt-1 ml-2 text-xs muted hover:underline" @click="expanded = !expanded">
      {{ expanded ? '收起' : `展开其余 ${part.sources.length - 4} 个` }}
    </button>
  </div>
</template>

<style scoped>
.cred {
  flex-shrink: 0;
  border-radius: 999px;
  padding: 0 0.45rem;
  font-size: 11px;
  font-weight: 600;
  background: var(--cs-line);
}
</style>
