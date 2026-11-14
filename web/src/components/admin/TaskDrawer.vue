<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ChevronRight, ExternalLink, FileDown, Loader2, MessageSquare } from 'lucide-vue-next'
import type { AdminTaskDetail } from '@/api/types'
import { api } from '@/api/client'
import DrawerTabs from '@/components/admin/DrawerTabs.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import SideDrawer from '@/components/common/SideDrawer.vue'
import { compact, duration, money, nodeLabel, revisionStatus, stepStatus, taskPastel } from '@/lib/adminFormat'
import { artifactKindLabel, formatBytes, formatTime, hostOf, modeLabel, relativeTime, taskStatusLabel } from '@/lib/format'
import { useToastStore } from '@/stores/toast'

/** 任务详情抽屉：概况 / 步骤 / 来源 / 成果 */
const STAGE_NAME: Record<string, string> = {
  files: '读取文件', plan: '规划搜索', search: '浏览器搜索', read: '读取网页', extract: '提取信息',
  coverage: '评估覆盖/补查', verify: '核验来源', build: '整理数据', analyze: '计算分析', write: '撰写成果',
}

const props = defineProps<{ taskId: string | null }>()
const emit = defineEmits<{ close: [] }>()
const toast = useToastStore()
const data = ref<AdminTaskDetail | null>(null)
const loading = ref(false)
const tab = ref<'summary' | 'steps' | 'sources' | 'artifacts'>('summary')
const openStep = ref<string | null>(null)

watch(
  () => props.taskId,
  async (id) => {
    data.value = null
    tab.value = 'summary'
    openStep.value = null
    if (!id) return
    loading.value = true
    try {
      const d = await api.adminTask(id)
      if (props.taskId === id) data.value = d
    } catch (e) {
      toast.error(e, '加载任务详情失败')
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

const open = computed({ get: () => !!props.taskId, set: (v: boolean) => !v && emit('close') })
const t = computed(() => data.value?.task)
const failedSteps = computed(() => data.value?.steps.filter((s) => s.step_status === 'failed').length ?? 0)
const srcTotal = computed(() => Object.values(data.value?.sources.by_status ?? {}).reduce((a, b) => a + b, 0))
const LIMIT_LABEL: Record<string, string> = {
  max_queries: '搜索次数',
  max_sources: '读取网页',
  max_llm_requests: '模型调用',
  max_records: '记录数',
}
</script>

<template>
  <SideDrawer v-model="open" title="任务详情" :width="760">
    <template #title>
      <div v-if="t" class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <StatusPill :tone="taskPastel(t.task_status)" :text="taskStatusLabel(t.task_status, t.status_reason)" />
          <span class="text-[12px] text-slate-400">{{ modeLabel(t.mode) }}</span>
        </div>
        <h2 class="mt-1.5 text-base leading-6 font-bold tracking-tight text-white">{{ t.title }}</h2>
        <div class="mt-0.5 flex flex-wrap gap-x-3 text-[12px] text-slate-400">
          <span>{{ t.display_name || t.username || '—' }}</span>
          <span>创建于 {{ formatTime(t.created_time) }}</span>
          <span>更新 {{ relativeTime(t.updated_time) }}</span>
          <span class="font-mono text-[11px] text-slate-500">{{ t.task_id }}</span>
        </div>
      </div>
      <div v-else class="flex items-center gap-2 text-sm text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> 加载中…</div>
    </template>
    <template #headerActions>
      <button v-if="t" class="btn-secondary btn-sm shrink-0" title="下载该任务的执行日志（排查用）" @click="api.downloadTaskTrace(t.task_id)">
        <FileDown class="h-3.5 w-3.5" /> 执行日志
      </button>
      <RouterLink v-if="t?.conversation_id" :to="{ name: 'chat', params: { id: t.conversation_id } }" class="btn-secondary btn-sm shrink-0">
        <MessageSquare class="h-3.5 w-3.5" /> 打开对话
      </RouterLink>
    </template>
    <template #tabs>
      <DrawerTabs
        v-if="data"
        v-model="tab"
        :tabs="[
          { value: 'summary', label: '概况' },
          { value: 'steps', label: '步骤', count: data.steps.length },
          { value: 'sources', label: '来源', count: srcTotal },
          { value: 'artifacts', label: '成果', count: data.artifacts.length },
        ]"
      />
    </template>

    <template v-if="data && t">
      <!-- 概况 -->
      <div v-if="tab === 'summary'" class="space-y-5">
        <div v-if="data.error_desc" class="rounded-lg border border-rose-300/40 px-3.5 py-2.5 text-[13px]">
          <div class="mb-1 font-semibold text-white">失败原因</div>
          <code class="ac-code">{{ data.error_desc }}</code>
        </div>
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <div class="rounded-lg border border-[var(--cs-line)] px-3 py-2.5">
            <div class="ac-caps">总耗时</div>
            <div class="mt-1 text-lg font-bold text-white tabular-nums">{{ duration(t.elapsed_ms) }}</div>
            <div class="text-[11px] text-slate-500">{{ ['queued', 'running', 'pausing', 'stopping'].includes(t.task_status) ? '进行中' : '开始到结束' }}</div>
          </div>
          <div class="rounded-lg border border-[var(--cs-line)] px-3 py-2.5">
            <div class="ac-caps">模型调用</div>
            <div class="mt-1 text-lg font-bold text-white tabular-nums">{{ compact(data.llm.requests) }}</div>
            <div class="text-[11px] text-slate-500">{{ data.llm.failed ? `${data.llm.failed} 次失败` : '无失败' }}</div>
          </div>
          <div class="rounded-lg border border-[var(--cs-line)] px-3 py-2.5">
            <div class="ac-caps">Token 入 / 出</div>
            <div class="mt-1 text-lg font-bold text-white tabular-nums">{{ compact(data.llm.input_tokens) }}<span class="text-sm text-slate-400"> / {{ compact(data.llm.output_tokens) }}</span></div>
          </div>
          <div class="rounded-lg border border-[var(--cs-line)] px-3 py-2.5">
            <div class="ac-caps">费用</div>
            <div class="mt-1 text-lg font-bold text-white tabular-nums">{{ money(t.spent_minor_amt, 'CNY') }}</div>
            <div v-if="t.cost_unknown_qty" class="text-[11px] text-amber-300">{{ t.cost_unknown_qty }} 次待核算</div>
          </div>
          <div class="rounded-lg border border-[var(--cs-line)] px-3 py-2.5">
            <div class="ac-caps">来源</div>
            <div class="mt-1 text-lg font-bold text-white tabular-nums">{{ data.sources.by_status.captured ?? 0 }}<span class="text-sm text-slate-400"> / {{ srcTotal }}</span></div>
            <div class="text-[11px] text-slate-500">已读取 / 尝试</div>
          </div>
        </div>

        <div v-if="t.stage_ms && Object.keys(t.stage_ms).length">
          <div class="ac-caps mb-2">各阶段耗时</div>
          <div class="flex flex-wrap gap-1.5">
            <span v-for="(ms, k) in t.stage_ms" :key="k" class="lim">{{ STAGE_NAME[k] ?? k }} {{ duration(ms) }}</span>
          </div>
        </div>

        <div>
          <div class="ac-caps mb-2">需求</div>
          <p class="text-[13px] leading-6 whitespace-pre-wrap text-slate-200">{{ data.spec.requirement_text || '—' }}</p>
          <ul v-if="data.spec.questions.length" class="mt-2 list-disc space-y-0.5 pl-5 text-[13px] text-slate-300">
            <li v-for="q in data.spec.questions" :key="q">{{ q }}</li>
          </ul>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <span v-for="(v, k) in data.spec.limits" :key="k" class="lim">{{ LIMIT_LABEL[k] ?? k }} ≤ {{ v }}</span>
            <span v-for="f in data.spec.output_formats" :key="f" class="lim uppercase">{{ f }}</span>
          </div>
        </div>

        <div>
          <div class="ac-caps mb-2">执行轮次</div>
          <table class="w-full text-[13px]">
            <thead>
              <tr class="text-left text-[12px] text-slate-400">
                <th class="py-1.5 font-medium">轮次</th>
                <th class="py-1.5 font-medium">状态</th>
                <th class="py-1.5 font-medium">开始</th>
                <th class="py-1.5 text-right font-medium">耗时</th>
                <th class="py-1.5 pl-4 font-medium">Worker</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in data.runs" :key="r.run_id" class="border-t border-[var(--cs-line)]">
                <td class="py-2 tabular-nums">#{{ r.run_seq_no }}</td>
                <td class="py-2"><StatusPill :tone="stepStatus(r.run_status).tone" :text="stepStatus(r.run_status).label" /></td>
                <td class="py-2 text-slate-300 tabular-nums">{{ formatTime(r.started_time) }}</td>
                <td class="py-2 text-right tabular-nums">{{ duration(r.duration_ms) }}</td>
                <td class="py-2 pl-4 font-mono text-[11px] text-slate-500">{{ r.worker_id || '—' }}</td>
              </tr>
              <tr v-if="!data.runs.length"><td colspan="5" class="py-3 text-slate-400">还没有执行</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 步骤 -->
      <div v-else-if="tab === 'steps'">
        <p class="mb-3 text-[12px] text-slate-400">共 {{ data.steps.length }} 步<template v-if="failedSteps">，{{ failedSteps }} 步失败（点击查看错误）</template>。暂停后继续时，已完成的步骤会被复用。</p>
        <ol class="overflow-hidden rounded-lg border border-[var(--cs-line)]">
          <li v-for="(st, i) in data.steps" :key="st.step_id" class="border-t border-[var(--cs-line)] first:border-t-0">
            <button
              type="button"
              class="flex w-full items-center gap-3 px-3 py-2 text-left text-[13px] hover:bg-[var(--cs-line)]"
              :class="st.error_desc ? '' : 'cursor-default'"
              :aria-expanded="openStep === st.step_id"
              @click="st.error_desc && (openStep = openStep === st.step_id ? null : st.step_id)"
            >
              <span class="w-6 shrink-0 text-right text-[11px] text-slate-500 tabular-nums">{{ i + 1 }}</span>
              <span class="w-24 shrink-0"><StatusPill :tone="stepStatus(st.step_status).tone" :text="stepStatus(st.step_status).label" /></span>
              <span class="min-w-0 flex-1">
                <span class="font-medium text-white">{{ nodeLabel(st.node_id) }}</span>
                <span v-if="st.role_label" class="ml-2 text-[12px] text-slate-400">{{ st.role_label }}</span>
                <span class="ml-2 truncate font-mono text-[11px] text-slate-500">{{ st.node_id }}</span>
              </span>
              <span v-if="st.attempt_no > 1" class="shrink-0 text-[11px] text-amber-300">第 {{ st.attempt_no }} 次</span>
              <span class="w-16 shrink-0 text-right text-[12px] text-slate-300 tabular-nums">{{ duration(st.duration_ms) }}</span>
              <ChevronRight v-if="st.error_desc" class="h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform" :class="openStep === st.step_id ? 'rotate-90' : ''" />
              <span v-else class="w-3.5 shrink-0" />
            </button>
            <div v-if="openStep === st.step_id && st.error_desc" class="px-3 pb-3 pl-12"><code class="ac-code">{{ st.error_desc }}</code></div>
          </li>
          <li v-if="!data.steps.length" class="px-3 py-6 text-center text-[13px] text-slate-400">还没有步骤记录</li>
        </ol>
      </div>

      <!-- 来源 -->
      <div v-else-if="tab === 'sources'">
        <div class="mb-3 flex flex-wrap gap-1.5">
          <span v-for="(n, st) in data.sources.by_status" :key="st" class="lim">{{ revisionStatus(String(st)).label }} {{ n }}</span>
        </div>
        <ul class="overflow-hidden rounded-lg border border-[var(--cs-line)]">
          <li v-for="(s, i) in data.sources.items" :key="i" class="flex items-start gap-3 border-t border-[var(--cs-line)] px-3 py-2.5 first:border-t-0">
            <span class="mt-0.5 w-6 shrink-0 text-right text-[12px] font-semibold text-slate-400 tabular-nums">{{ s.source_no ?? '—' }}</span>
            <span class="min-w-0 flex-1">
              <a :href="s.url" target="_blank" rel="noopener" class="group flex items-center gap-1 text-[13px] font-medium text-white hover:underline">
                <span class="truncate">{{ s.title || s.url }}</span>
                <ExternalLink class="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-60" />
              </a>
              <span class="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-slate-500">
                <span>{{ s.site_name || hostOf(s.url) }}</span>
                <span>· {{ s.credibility_label }}</span>
                <span v-if="s.failure_reason" class="text-amber-300">· {{ s.failure_reason }}</span>
              </span>
            </span>
            <StatusPill :tone="revisionStatus(s.revision_status).tone" :text="revisionStatus(s.revision_status).label" />
          </li>
          <li v-if="!data.sources.items.length" class="px-3 py-6 text-center text-[13px] text-slate-400">没有读取任何来源</li>
        </ul>
      </div>

      <!-- 成果 -->
      <div v-else>
        <ul class="overflow-hidden rounded-lg border border-[var(--cs-line)]">
          <li v-for="a in data.artifacts" :key="a.artifact_id" class="flex items-center gap-3 border-t border-[var(--cs-line)] px-3 py-2.5 text-[13px] first:border-t-0">
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium text-white">{{ a.display_name }}</span>
              <span class="text-[11px] text-slate-500">{{ artifactKindLabel(a.artifact_kind) }} · {{ formatBytes(a.byte_qty) }}<template v-if="a.record_qty != null"> · {{ a.record_qty }} 条记录</template></span>
            </span>
            <span class="shrink-0 text-[12px] text-slate-400">{{ formatTime(a.created_time) }}</span>
          </li>
          <li v-if="!data.artifacts.length" class="px-3 py-6 text-center text-[13px] text-slate-400">没有生成文件</li>
        </ul>
      </div>
    </template>
  </SideDrawer>
</template>

<style scoped>
.lim {
  display: inline-flex;
  border: 1px solid var(--cs-line-strong);
  border-radius: 6px;
  padding: 0 7px;
  font-size: 11px;
  line-height: 20px;
  color: var(--color-slate-300);
}
</style>
