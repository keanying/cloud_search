<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ExternalLink, Quote, Search } from 'lucide-vue-next'
import type { TaskSourcesOut } from '@/api/types'
import { api } from '@/api/client'
import { ACCESS_METHOD_LABEL, ACTIVE_STATUSES, formatTime, hostOf, qualityLabel } from '@/lib/format'
import { useChatStore } from '@/stores/chat'
import EmptyState from '@/components/common/EmptyState.vue'

const props = defineProps<{ taskId: string | null; focusN: number | null }>()
const chat = useChatStore()
const data = ref<TaskSourcesOut | null>(null)
const error = ref<string | null>(null)
const root = ref<HTMLElement | null>(null)
const showCandidates = ref(false)
let timer: number | undefined

const read = computed(() => (data.value?.sources ?? []).filter((s) => s.revision_status === 'captured'))
const failed = computed(() => (data.value?.sources ?? []).filter((s) => s.revision_status !== 'captured'))
const candidates = computed(() => data.value?.candidates ?? [])

const REVISION_LABEL: Record<string, string> = {
  no_content: '无正文',
  blocked: '访问受限',
  failed: '读取失败',
}

async function load() {
  if (!props.taskId) return
  try {
    data.value = await api.taskSources(props.taskId)
    error.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  }
}

async function focus() {
  if (props.focusN == null) return
  await nextTick()
  const el = root.value?.querySelector(`[data-n="${props.focusN}"]`)
  el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

watch(
  () => props.taskId,
  async () => {
    data.value = null
    window.clearInterval(timer)
    await load()
    void focus()
    timer = window.setInterval(() => {
      const t = props.taskId ? chat.tasks[props.taskId] : null
      if (t && ACTIVE_STATUSES.has(t.task_status)) void load()
    }, 5000)
  },
  { immediate: true },
)
watch(() => props.focusN, focus)
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div ref="root" class="h-full overflow-y-auto p-3">
    <div v-if="error" class="mb-2 text-sm text-rose-300">{{ error }}</div>
    <EmptyState v-if="data && !data.sources.length && !data.candidates.length" title="暂无来源" desc="任务读取网页后，来源会出现在这里" />

    <section v-if="read.length" class="mb-4">
      <h3 class="mb-2 text-xs font-semibold tracking-wide text-slate-400">已读取来源（{{ read.length }}）</h3>
      <ul class="space-y-2">
        <li
          v-for="s in read"
          :key="s.source_revision_id"
          :data-n="s.n"
          class="rounded-xl border p-3 transition-colors"
          :class="focusN === s.n ? 'border-brand-400/70 bg-brand-500/10' : 'border-white/10 bg-white/[0.03]'"
        >
          <div class="flex items-start gap-2">
            <span class="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-md bg-brand-500/25 px-1 text-[11px] font-semibold text-brand-300">{{ s.n }}</span>
            <div class="min-w-0 flex-1">
              <a
                :href="s.final_url || s.request_url"
                target="_blank"
                rel="noopener noreferrer nofollow"
                class="group inline-flex items-start gap-1 text-sm font-medium text-white hover:text-brand-300"
              >
                <span class="line-clamp-2">{{ s.title || s.final_url || s.request_url }}</span>
                <ExternalLink class="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-60 group-hover:opacity-100" />
              </a>
              <div class="mt-0.5 truncate text-xs text-slate-500">{{ s.final_url || s.request_url }}</div>
              <div class="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-400">
                <span>发布主体：{{ s.site_name || hostOf(s.final_url || s.request_url) || '未知' }}</span>
                <span v-if="s.author">作者：{{ s.author }}</span>
                <span>发布时间：{{ s.publish_time_text || '未知' }}</span>
                <span>读取于 {{ formatTime(s.retrieved_time) }}</span>
                <span>{{ ACCESS_METHOD_LABEL[s.access_method] || s.access_method }}</span>
              </div>
              <ul v-if="s.evidence.length" class="mt-2 space-y-1.5">
                <li v-for="ev in s.evidence" :key="ev.evidence_id" class="rounded-lg bg-white/5 p-2 text-xs">
                  <div class="flex gap-1.5 text-slate-300">
                    <Quote class="mt-0.5 h-3 w-3 shrink-0 text-slate-500" />
                    <span class="italic">{{ ev.quote_text }}</span>
                  </div>
                  <div v-if="ev.claim_text" class="mt-1 text-slate-400">→ {{ ev.claim_text }}</div>
                  <div class="mt-1 text-[11px] text-slate-500">{{ qualityLabel(ev.verification_status) }}</div>
                </li>
              </ul>
            </div>
          </div>
        </li>
      </ul>
    </section>

    <section v-if="failed.length" class="mb-4">
      <h3 class="mb-2 text-xs font-semibold tracking-wide text-slate-400">访问受限或读取失败（{{ failed.length }}）</h3>
      <ul class="space-y-1.5">
        <li v-for="s in failed" :key="s.source_revision_id" :data-n="s.n" class="rounded-lg border border-white/5 px-3 py-2 text-xs">
          <div class="truncate text-slate-300">{{ s.title || s.request_url }}</div>
          <div class="text-slate-500">
            {{ REVISION_LABEL[s.revision_status] || s.revision_status }}<template v-if="s.failure_reason">：{{ s.failure_reason }}</template>
          </div>
        </li>
      </ul>
    </section>

    <section v-if="candidates.length">
      <button class="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-slate-400 hover:text-white" :aria-expanded="showCandidates" @click="showCandidates = !showCandidates">
        <Search class="h-3.5 w-3.5" /> 搜索候选（{{ candidates.length }}，仅为线索，未经读取不作为证据）
      </button>
      <ul v-if="showCandidates" class="space-y-1.5">
        <li v-for="c in candidates" :key="c.candidate_id" class="rounded-lg border border-white/5 px-3 py-2 text-xs">
          <a :href="c.url" target="_blank" rel="noopener noreferrer nofollow" class="text-slate-200 hover:text-brand-300">{{ c.title || c.url }}</a>
          <div class="truncate text-slate-500">{{ c.url }}</div>
          <div v-if="c.snippet" class="mt-1 line-clamp-2 text-slate-400">{{ c.snippet }}</div>
          <div class="mt-1 text-[11px] text-slate-500">「{{ c.query_text }}」· {{ c.engine_name }} 第 {{ c.rank_no }} 位 · {{ c.candidate_status }}</div>
        </li>
      </ul>
    </section>
  </div>
</template>
