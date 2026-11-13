<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Download, Eye, MessageSquare, X } from 'lucide-vue-next'
import type { ArtifactOut } from '@/api/types'
import { api } from '@/api/client'
import ArtifactPanel from '@/components/panel/ArtifactPanel.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatTiles from '@/components/task/StatTiles.vue'
import { FORMAT_TONE, formatOfName } from '@/lib/artifactFormats'
import { artifactKindLabel, formatBytes, qualityLabel, relativeTime } from '@/lib/format'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const items = ref<ArtifactOut[]>([])
const loaded = ref(false)
const filter = ref<'all' | 'data' | 'report' | 'other'>('all')
const previewId = ref<string | null>(null)

const FILTERS = [
  { v: 'all', label: '全部', emoji: '🗂️' },
  { v: 'report', label: '报告', emoji: '📝' },
  { v: 'data', label: '数据', emoji: '📊' },
  { v: 'other', label: '其他文件', emoji: '📎' },
] as const

function group(a: ArtifactOut): 'data' | 'report' | 'other' {
  if (a.artifact_kind === 'dataset' || a.artifact_kind === 'data_dictionary') return 'data'
  if (a.artifact_kind === 'report' || a.artifact_kind === 'answer') return 'report'
  return 'other'
}

const counts = computed(() => ({
  report: items.value.filter((a) => group(a) === 'report').length,
  data: items.value.filter((a) => group(a) === 'data').length,
}))

/** 文件类型配色：Word 紫、PDF 桃、Excel 绿、HTML 蓝… */
function toneOf(a: ArtifactOut): string {
  const f = formatOfName(a.display_name)
  if (f) return FORMAT_TONE[f]
  return group(a) === 'data' ? 'mint' : 'sky'
}
function extOf(a: ArtifactOut): string {
  return formatOfName(a.display_name) ?? (a.display_name.match(/\.([A-Za-z0-9]{1,5})$/)?.[1] ?? 'file')
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
  <div class="flex h-full gap-3 p-3">
    <div class="min-w-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-6xl px-4 pt-3 pb-12 md:px-6">
        <PageHeader title="我的成果" desc="对话中生成的报告与数据文件。每个文件对应固定版本，修订会生成新文件。" :parent="{ name: 'home' }">
          <StatTiles
            class="w-full sm:w-[360px]"
            :items="[
              { label: '报告', value: counts.report, tone: 'lilac' },
              { label: '数据', value: counts.data, tone: 'mint' },
              { label: '全部', value: items.length, tone: 'butter' },
            ]"
          />
        </PageHeader>

        <div class="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="筛选成果">
          <button
            v-for="f in FILTERS"
            :key="f.v"
            role="tab"
            :aria-selected="filter === f.v"
            class="chip"
            :class="filter === f.v ? 'chip-active' : ''"
            @click="filter = f.v"
          >
            {{ f.emoji }} {{ f.label }}
          </button>
        </div>

        <div v-if="loaded && !shown.length" class="surface flex flex-col items-center px-6 py-14 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-full card-sky text-2xl" aria-hidden="true">📂</span>
          <h2 class="mt-4 text-lg font-bold text-white">你的数据和报告会出现在这里</h2>
          <p class="mt-1 text-sm text-slate-400">在对话中提出采集或研究需求即可生成</p>
          <RouterLink to="/" class="btn-primary mt-5">开始一个新对话</RouterLink>
        </div>

        <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <li
            v-for="a in shown"
            :key="a.artifact_id"
            class="flex flex-col p-5 transition hover:-translate-y-0.5"
            :class="`card-${toneOf(a)}`"
          >
            <div class="flex items-start gap-3">
              <span class="flex h-12 min-w-12 items-center justify-center rounded-2xl bg-[var(--cs-surface-solid)] px-2 text-xs font-extrabold tracking-wide uppercase accent-ink">
                {{ extOf(a) }}
              </span>
              <div class="flex-1" />
              <RouterLink
                v-if="a.conversation_id"
                :to="{ name: 'chat', params: { id: a.conversation_id } }"
                class="round-btn-light !h-9 !w-9"
                aria-label="回到形成该成果的对话"
                title="回到对话"
              >
                <MessageSquare class="h-4 w-4" />
              </RouterLink>
            </div>
            <div class="mt-4 line-clamp-2 min-h-12 text-[15px] leading-6 font-bold tracking-tight text-white" :title="a.display_name">
              {{ a.display_name }}
            </div>
            <div class="mt-1 flex flex-wrap gap-x-2 text-xs text-slate-300">
              <span>{{ artifactKindLabel(a.artifact_kind) }}</span>
              <span v-if="a.record_qty != null">{{ a.record_qty }} 条记录</span>
              <span>{{ formatBytes(a.byte_qty) }}</span>
              <span>{{ relativeTime(a.created_time) }}</span>
            </div>
            <div class="mt-auto flex flex-wrap items-center gap-2 pt-4">
              <span class="pill bg-[var(--cs-surface-solid)] text-slate-300">{{ qualityLabel(a.quality_status) }}</span>
              <span v-if="a.artifact_status !== 'available'" class="pill card-peach accent-ink">{{ a.artifact_status }}</span>
              <div class="flex-1" />
              <button class="btn-secondary btn-sm" @click="previewId = a.artifact_id"><Eye class="h-3.5 w-3.5" /> 预览</button>
              <button class="btn-primary btn-sm" :disabled="a.artifact_status !== 'available'" @click="download(a)">
                <Download class="h-3.5 w-3.5" /> 下载
              </button>
            </div>
          </li>
        </ul>
      </div>
    </div>
    <aside
      v-if="previewId"
      class="glass-strong fixed inset-0 z-40 flex w-full flex-col !rounded-none lg:relative lg:inset-auto lg:w-[45%] lg:max-w-3xl lg:!rounded-[28px]"
      aria-label="成果预览"
    >
      <header class="hairline flex items-center justify-between border-b py-2.5 pr-2.5 pl-5">
        <span class="text-sm font-bold">成果预览</span>
        <button class="round-btn-light !h-9 !w-9" aria-label="关闭预览" @click="previewId = null"><X class="h-4 w-4" /></button>
      </header>
      <div class="min-h-0 flex-1"><ArtifactPanel :artifact-id="previewId" /></div>
    </aside>
  </div>
</template>
