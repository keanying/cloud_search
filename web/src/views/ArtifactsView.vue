<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Download, Eye, FileSpreadsheet, FileText, MessageSquare, X } from 'lucide-vue-next'
import type { ArtifactOut } from '@/api/types'
import { api } from '@/api/client'
import ArtifactPanel from '@/components/panel/ArtifactPanel.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { artifactKindLabel, formatBytes, qualityLabel, relativeTime } from '@/lib/format'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const items = ref<ArtifactOut[]>([])
const loaded = ref(false)
const filter = ref<'all' | 'data' | 'report' | 'other'>('all')
const previewId = ref<string | null>(null)

const FILTERS = [
  { v: 'all', label: '全部' },
  { v: 'data', label: '数据' },
  { v: 'report', label: '报告' },
  { v: 'other', label: '其他文件' },
] as const

function group(a: ArtifactOut): 'data' | 'report' | 'other' {
  if (a.artifact_kind === 'dataset' || a.artifact_kind === 'data_dictionary') return 'data'
  if (a.artifact_kind === 'report' || a.artifact_kind === 'answer') return 'report'
  return 'other'
}

const shown = computed(() => (filter.value === 'all' ? items.value : items.value.filter((a) => group(a) === filter.value)))

onMounted(async () => {
  try {
    items.value = await api.listArtifacts()
  } catch (e) {
    toast.error(e)
  } finally {
    loaded.value = true
  }
})

async function download(a: ArtifactOut) {
  try {
    await api.downloadArtifact(a.artifact_id, a.display_name)
  } catch (e) {
    toast.error(e, '下载失败')
  }
}
</script>

<template>
  <div class="flex h-full">
    <div class="min-w-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-4xl px-4 py-6">
        <h1 class="text-xl font-semibold text-white">我的成果</h1>
        <p class="mt-1 text-sm text-slate-400">对话中生成的数据文件与报告。每个文件对应固定版本，修订会生成新文件。</p>
        <div class="mt-4 flex gap-2" role="tablist">
          <button
            v-for="f in FILTERS"
            :key="f.v"
            role="tab"
            :aria-selected="filter === f.v"
            class="rounded-full px-3 py-1 text-sm"
            :class="filter === f.v ? 'bg-brand-500/25 text-white' : 'text-slate-400 hover:text-white'"
            @click="filter = f.v"
          >
            {{ f.label }}
          </button>
        </div>
        <EmptyState v-if="loaded && !shown.length" class="glass mt-6" title="你的数据和报告会出现在这里" desc="在对话中提出采集或研究需求即可生成" />
        <ul class="mt-4 space-y-2">
          <li v-for="a in shown" :key="a.artifact_id" class="glass flex items-center gap-3 p-3">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500/20">
              <FileSpreadsheet v-if="group(a) === 'data'" class="h-5 w-5 text-brand-300" />
              <FileText v-else class="h-5 w-5 text-brand-300" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-medium text-white">{{ a.display_name }}</div>
              <div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-slate-400">
                <span>{{ artifactKindLabel(a.artifact_kind) }}</span>
                <span v-if="a.record_qty != null">{{ a.record_qty }} 条记录</span>
                <span>{{ formatBytes(a.byte_qty) }}</span>
                <span>{{ qualityLabel(a.quality_status) }}</span>
                <span>{{ relativeTime(a.created_time) }}</span>
                <span v-if="a.artifact_status !== 'available'" class="text-amber-300">{{ a.artifact_status }}</span>
              </div>
            </div>
            <RouterLink
              v-if="a.conversation_id"
              :to="{ name: 'chat', params: { id: a.conversation_id } }"
              class="icon-btn"
              aria-label="回到形成该成果的对话"
              title="回到对话"
            >
              <MessageSquare class="h-4 w-4" />
            </RouterLink>
            <button class="btn-secondary btn-sm" @click="previewId = a.artifact_id"><Eye class="h-3.5 w-3.5" /> 预览</button>
            <button class="btn-primary btn-sm" :disabled="a.artifact_status !== 'available'" @click="download(a)">
              <Download class="h-3.5 w-3.5" /> 下载
            </button>
          </li>
        </ul>
      </div>
    </div>
    <aside v-if="previewId" class="glass-strong fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col rounded-none lg:relative lg:my-3 lg:mr-3 lg:w-[45%] lg:rounded-2xl" aria-label="成果预览">
      <header class="flex items-center justify-between border-b border-white/10 px-3 py-2">
        <span class="text-sm font-medium">成果预览</span>
        <button class="icon-btn" aria-label="关闭预览" @click="previewId = null"><X class="h-4 w-4" /></button>
      </header>
      <div class="min-h-0 flex-1"><ArtifactPanel :artifact-id="previewId" /></div>
    </aside>
  </div>
</template>
