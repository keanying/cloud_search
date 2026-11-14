<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowUpRight, ChevronDown, Download, FileBarChart, FileSpreadsheet, FileText, Globe, Library, Paperclip, X } from 'lucide-vue-next'
import type { ArtifactFormat, ArtifactPart, ProgressPart, SourceOut, TakeoverPart as TakeoverPartT } from '@/api/types'
import { api } from '@/api/client'
import {
  ACTIVE_STATUSES,
  artifactKindLabel,
  hostOf,
  modeLabel,
  relativeTime,
  taskStatusEmoji,
  taskStatusLabel,
  taskStatusTone,
} from '@/lib/format'
import { FORMAT_LABEL, FORMAT_TONE, downloadFormat, partFormats, previewArtifactId } from '@/lib/artifactFormats'
import { useChatStore } from '@/stores/chat'
import { usePrefsStore } from '@/stores/prefs'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'
import StatusBadge from '@/components/common/StatusBadge.vue'
import TakeoverPart from '@/components/parts/TakeoverPart.vue'
import StageTimeline from './StageTimeline.vue'
import StatTiles from './StatTiles.vue'
import FileCard from '@/components/files/FileCard.vue'
import MiniBrowser from './MiniBrowser.vue'
import { fileIdFromUrl } from '@/lib/fileTypes'

/** 右侧“本次任务”看板：统计、阶段时间线、人工协助、最新来源、成果 */
defineProps<{ closable?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const chat = useChatStore()
const prefs = usePrefsStore()
const panel = usePanelStore()
const toast = useToastStore()

const allParts = computed(() => chat.messages.flatMap((m) => m.parts))

/** 对话中出现过的任务（按出现顺序） */
const taskIds = computed(() => {
  const ids: string[] = []
  for (const m of chat.messages) {
    for (const id of m.task_ids ?? []) if (!ids.includes(id)) ids.push(id)
    for (const p of m.parts) {
      const id = (p as { task_id?: string }).task_id
      if (id && !ids.includes(id)) ids.push(id)
    }
  }
  for (const [id, t] of Object.entries(chat.tasks)) {
    // 只收本对话的任务（防止其他对话的任务出现在“本次任务”里）
    if (t.conversation_id && t.conversation_id !== chat.conversationId) continue
    if (!ids.includes(id)) ids.push(id)
  }
  return ids
})

const picked = ref<string | null>(null)
watch(
  () => chat.conversationId,
  () => (picked.value = null),
)
/** 当前任务：用户选择 > 最近一个执行中的 > 最近一个 */
const taskId = computed(() => {
  if (picked.value && taskIds.value.includes(picked.value)) return picked.value
  const active = [...taskIds.value].reverse().find((id) => ACTIVE_STATUSES.has(chat.tasks[id]?.task_status ?? ''))
  return active ?? taskIds.value[taskIds.value.length - 1] ?? null
})
const task = computed(() => (taskId.value ? chat.tasks[taskId.value] : undefined))

function lastPart<T>(type: string, id: string | null): T | undefined {
  if (!id) return undefined
  for (let i = allParts.value.length - 1; i >= 0; i--) {
    const p = allParts.value[i] as { type: string; task_id?: string }
    if (p.type === type && p.task_id === id) return p as T
  }
  return undefined
}
const progress = computed(() => lastPart<ProgressPart>('progress', taskId.value))
/** 文件：有选中任务时只显示该任务用到的文件；还没有任务时显示对话里的文件 */
const taskFiles = computed(() => {
  if (!taskId.value) return chat.sentFiles
  const ids = ((task.value?.task_spec as { scope?: { file_ids?: string[] } } | undefined)?.scope?.file_ids) ?? []
  return chat.sentFiles.filter((f) => ids.includes(f.file_id))
})
const status = computed(() => task.value?.task_status ?? progress.value?.task_status ?? null)
const active = computed(() => ACTIVE_STATUSES.has(status.value ?? ''))
const takeover = computed(() => {
  const t = lastPart<TakeoverPartT>('takeover', taskId.value)
  return t && (t.state === 'requested' || t.state === 'active') ? t : undefined
})

const stats = computed(() => {
  const c = progress.value?.counters ?? {}
  return [
    { label: '搜索', value: c.queries ?? 0, tone: 'sky' as const },
    { label: '已读来源', value: c.sources_read ?? 0, tone: 'mint' as const },
    { label: '证据', value: c.evidence ?? 0, tone: 'lilac' as const },
  ]
})

/** 成果：按 artifact_id 去重，最新在前 */
const outputs = computed(() => {
  const seen = new Set<string>()
  const out: ArtifactPart[] = []
  for (let i = allParts.value.length - 1; i >= 0; i--) {
    const p = allParts.value[i]
    if (p.type !== 'artifact') continue
    const a = p as ArtifactPart
    if (a.task_id !== taskId.value) continue // 只显示当前任务的成果
    if (seen.has(a.artifact_id)) continue
    seen.add(a.artifact_id)
    out.push(a)
  }
  return out
})

// ---------------------------------------------------------------- 最新来源（随已读数量变化刷新）
const sources = ref<SourceOut[]>([])
let timer: number | undefined
async function loadSources(id: string) {
  try {
    const res = await api.taskSources(id)
    if (taskId.value !== id) return
    sources.value = [...res.sources]
      .filter((s) => s.revision_status === 'captured') // 只显示本任务实际读到的来源
      .sort((a, b) => (a.retrieved_time < b.retrieved_time ? 1 : -1))
      .slice(0, 5)
  } catch {
    /* 来源列表是辅助信息，失败时静默 */
  }
}
watch(
  () => [taskId.value, progress.value?.counters?.sources_read ?? 0] as const,
  ([id], before) => {
    window.clearTimeout(timer)
    if (!id) {
      sources.value = []
      return
    }
    if (!before || before[0] !== id) sources.value = []
    timer = window.setTimeout(() => void loadSources(id), before && before[0] === id ? 1200 : 0)
  },
  { immediate: true },
)
onBeforeUnmount(() => window.clearTimeout(timer))

const busy = ref<string | null>(null)
async function dl(a: ArtifactPart, f: ArtifactFormat) {
  busy.value = f.artifact_id
  try {
    await downloadFormat(a, f)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    busy.value = null
  }
}
function previewOutput(a: ArtifactPart) {
  panel.openArtifact(previewArtifactId(a), a.task_id, partFormats(a), a.display_name)
}
function outputIcon(a: ArtifactPart) {
  if (a.artifact_kind === 'dataset' || /csv|sheet|excel/.test(a.mime_name)) return FileSpreadsheet
  if (a.artifact_kind === 'report') return FileBarChart
  return FileText
}
function outputTone(a: ArtifactPart) {
  if (a.artifact_kind === 'dataset' || /csv|sheet|excel/.test(a.mime_name)) return 'card-mint'
  if (a.artifact_kind === 'report') return 'card-lilac'
  return 'card-sky'
}
const BADGE_TONES = ['card-mint', 'card-lilac', 'card-butter', 'card-sky', 'card-peach']
function badgeTone(s: SourceOut) {
  const h = hostOf(s.final_url || s.request_url)
  let n = 0
  for (const ch of h) n = (n + ch.charCodeAt(0)) % 997
  return BADGE_TONES[n % BADGE_TONES.length]
}
function sourceFileId(s: SourceOut): string | null {
  return s.access_method === 'user_file' ? fileIdFromUrl(s.final_url || s.request_url) : null
}
function siteName(s: SourceOut) {
  return s.site_name || hostOf(s.final_url || s.request_url).replace(/^www\./, '')
}
</script>

<template>
  <aside class="flex h-full min-h-0 flex-col" aria-label="本次任务">
    <header class="flex items-center gap-2 px-1 pb-3">
      <h2 class="text-lg font-bold tracking-tight text-white">本次任务</h2>
      <StatusBadge v-if="status" :tone="taskStatusTone(status)" :emoji="taskStatusEmoji(status, task?.status_reason)">
        {{ taskStatusLabel(status, task?.status_reason) }}
      </StatusBadge>
      <div class="flex-1" />
      <button v-if="closable" class="round-btn-light !h-9 !w-9" aria-label="关闭任务看板" @click="emit('close')">
        <X class="h-4 w-4" />
      </button>
    </header>

    <div class="-mx-1 min-h-0 flex-1 space-y-3 overflow-y-auto px-1 pt-1 pb-3">
      <!-- 空状态 -->
      <div v-if="!taskId" class="surface p-5">
        <div class="flex h-11 w-11 items-center justify-center rounded-full card-butter text-xl" aria-hidden="true">🧭</div>
        <h3 class="mt-3 text-base font-bold text-white">还没有任务</h3>
        <p class="mt-1 text-sm text-slate-400">在下方描述你的需求。开始执行后，这里会显示搜索进度、已读来源和生成的文件。</p>
      </div>

      <template v-else>
        <!-- 统计 -->
        <StatTiles :items="stats" />

        <!-- 当前任务 -->
        <section class="surface p-4">
          <div class="flex items-start gap-2">
            <div class="min-w-0 flex-1">
              <div class="text-[15px] leading-6 font-bold tracking-tight text-white">{{ task?.title || '任务' }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                <span v-if="task?.mode" class="pill sunken hairline border text-slate-300">{{ modeLabel(task.mode) }}</span>
                <span v-if="task?.updated_time">更新于 {{ relativeTime(task.updated_time) }}</span>
              </div>
            </div>
            <label v-if="taskIds.length > 1" class="relative shrink-0">
              <span class="sr-only">切换任务</span>
              <select
                :value="taskId ?? ''"
                class="sunken hairline appearance-none rounded-full border py-1 pr-7 pl-3 text-xs font-semibold text-slate-200"
                @change="picked = ($event.target as HTMLSelectElement).value"
              >
                <option v-for="(id, i) in taskIds" :key="id" :value="id">任务 {{ i + 1 }}</option>
              </select>
              <ChevronDown class="pointer-events-none absolute top-1/2 right-2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            </label>
          </div>
          <div v-if="progress?.stages?.length" class="card-mint mt-4 p-4">
            <StageTimeline :stages="progress.stages" dense />
          </div>
          <p v-else class="mt-3 text-sm text-slate-400">{{ status === 'draft' ? '等待你确认执行计划' : '准备中…' }}</p>
          <p v-if="task?.error_desc && (status === 'failed' || status === 'partial_failed')" class="mt-3 text-xs text-rose-300">
            {{ task.error_desc }}
          </p>
          <div class="mt-4 flex flex-wrap gap-2">
            <button v-if="progress?.browser_available" class="btn-primary btn-sm" @click="panel.openBrowserModal(taskId!)">
              <Globe class="h-3.5 w-3.5" /> {{ active ? '看它在读什么' : '浏览器记录' }}
            </button>
            <button class="btn-secondary btn-sm" @click="panel.openSources(taskId!)">
              <Library class="h-3.5 w-3.5" /> 全部来源
            </button>
          </div>
        </section>

        <!-- 人工协助 -->
        <div v-if="takeover" class="px-1 py-2">
          <TakeoverPart :part="takeover" compact />
        </div>

        <!-- 最新来源 -->
        <section v-if="sources.length" class="surface p-4">
          <div class="mb-2 flex items-center">
            <h3 class="text-sm font-bold text-white">最新来源</h3>
            <div class="flex-1" />
            <button class="text-xs font-semibold text-slate-400 hover:text-white" @click="panel.openSources(taskId!)">查看全部</button>
          </div>
          <ul class="-mx-1">
            <li v-for="s in sources" :key="s.source_revision_id">
              <button
                v-if="sourceFileId(s)"
                type="button"
                class="group flex w-full items-center gap-3 rounded-2xl px-1 py-1.5 text-left hover:bg-white/5"
                @click="panel.openFile(sourceFileId(s)!)"
              >
                <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl card-mint accent-ink">
                  <FileText class="h-4 w-4" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-xs text-slate-400">你上传的文件</span>
                  <span class="block truncate text-sm font-medium text-slate-100">{{ s.title }}</span>
                </span>
              </button>
              <a
                v-else
                :href="s.final_url || s.request_url"
                target="_blank"
                rel="noopener noreferrer"
                class="group flex items-center gap-3 rounded-2xl px-1 py-1.5 hover:bg-white/5"
              >
                <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-sm font-bold uppercase accent-ink" :class="badgeTone(s)">
                  {{ siteName(s).slice(0, 1) }}
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-xs text-slate-400">{{ siteName(s) }}</span>
                  <span class="block truncate text-sm font-medium text-slate-100">{{ s.title || s.final_url || s.request_url }}</span>
                </span>
                <ArrowUpRight class="h-4 w-4 shrink-0 text-slate-500 opacity-0 transition group-hover:opacity-100" />
              </a>
            </li>
          </ul>
        </section>
      </template>

      <!-- 对话中的文件 -->
      <section v-if="taskFiles.length" class="surface p-4">
        <h3 class="mb-2 flex items-center gap-1.5 text-sm font-bold text-white">
          <Paperclip class="h-4 w-4" /> {{ taskId ? '本次使用的文件' : '对话中的文件' }}
          <span class="text-xs font-semibold text-slate-400">{{ taskFiles.length }}</span>
        </h3>
        <div class="space-y-1.5">
          <FileCard
            v-for="f in taskFiles"
            :key="f.file_id"
            compact
            :name="f.name"
            :ext="f.ext"
            :byte-qty="f.byte_qty"
            :status="f.parse_status"
            :pages="f.page_qty"
            :parser="f.parser"
            :detail="f.parse_detail"
            :error="f.parse_error"
            @open="panel.openFile(f.file_id)"
          />
        </div>
      </section>

      <!-- 成果 -->
      <section v-if="outputs.length" class="surface p-4">
        <h3 class="mb-2 text-sm font-bold text-white">成果</h3>
        <ul class="space-y-2">
          <li v-for="a in outputs" :key="a.artifact_id" class="sunken rounded-2xl p-2.5">
            <button class="flex w-full items-center gap-3 text-left" :title="`预览 ${a.display_name}`" @click="previewOutput(a)">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl" :class="outputTone(a)">
                <component :is="outputIcon(a)" class="h-4 w-4 accent-ink" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-slate-100">{{ a.display_name.replace(/\.[A-Za-z0-9]{1,5}$/, '') }}</span>
                <span class="block text-xs text-slate-400">{{ artifactKindLabel(a.artifact_kind) }}<template v-if="a.record_qty != null"> · {{ a.record_qty }} 条</template></span>
              </span>
            </button>
            <div v-if="partFormats(a).length" class="mt-2 flex flex-wrap gap-1.5 pl-12">
              <button
                v-for="f in partFormats(a)"
                :key="f.artifact_id"
                class="pill bg-[var(--cs-surface-solid)] text-slate-200 hover:text-white"
                :disabled="busy === f.artifact_id"
                :title="`下载 ${FORMAT_LABEL[f.format]}`"
                @click="dl(a, f)"
              >
                <span class="h-2 w-2 rounded-full" :style="{ background: `var(--pastel-${FORMAT_TONE[f.format]}-dot)` }" />
                {{ FORMAT_LABEL[f.format] }}
                <Download class="h-3 w-3 opacity-50" />
              </button>
            </div>
          </li>
        </ul>
      </section>

      <!-- 搜索/读取网页时的浏览器小窗（点击放大） -->
      <MiniBrowser v-if="taskId && prefs.autoOpenBrowser" :task-id="taskId" :active="active" />
    </div>
  </aside>
</template>
