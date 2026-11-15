<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bug, Download, FileArchive, Loader2, RefreshCw, Search } from 'lucide-vue-next'
import type { AdminDebugStatus, AdminTask } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
import ToggleSwitch from '@/components/common/ToggleSwitch.vue'
import { formatBytes, formatTime, taskStatusLabel } from '@/lib/format'
import { useToastStore } from '@/stores/toast'

/** 调试日志：开关详细调试记录；按任务或全系统下载日志包（ZIP），用于分析问题 */
const toast = useToastStore()
const status = ref<AdminDebugStatus | null>(null)
const enabled = ref(false)
const saving = ref(false)
const hours = ref(24)
const includeText = ref(true)
const busy = ref<string | null>(null)
const tasks = ref<AdminTask[]>([])
const q = ref('')

async function load() {
  try {
    status.value = await api.adminDebugStatus()
    enabled.value = status.value.enabled
  } catch (e) {
    toast.error(e, '读取调试日志状态失败')
  }
}
async function loadTasks() {
  try {
    tasks.value = (await api.adminTasks({ page: 1, size: 12, q: q.value.trim() || undefined })).items
  } catch (e) {
    toast.error(e, '读取任务失败')
  }
}
onMounted(() => {
  void load()
  void loadTasks()
})

async function toggle(v: boolean) {
  saving.value = true
  try {
    await api.putAdminSettings({ logs_debug: v })
    enabled.value = v
    toast.push(v ? '已开启详细调试记录，新的调用与任务会完整记录' : '已关闭详细调试记录', 'success')
    setTimeout(load, 800)
  } catch (e) {
    enabled.value = !v
    toast.error(e, '保存失败')
  } finally {
    saving.value = false
  }
}

async function download(taskId?: string) {
  busy.value = taskId ?? 'system'
  try {
    await api.downloadDebugBundle({ taskId, hours: hours.value, includeText: includeText.value })
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    busy.value = null
  }
}

const debugBytes = computed(() => (status.value?.files ?? []).reduce((n, f) => n + f.bytes, 0))
const RANGES = [
  { value: 1, label: '1 小时' },
  { value: 6, label: '6 小时' },
  { value: 24, label: '24 小时' },
  { value: 72, label: '3 天' },
  { value: 168, label: '7 天' },
]
const CONTENTS = [
  ['智能体', '每个智能体每次调用的完整提示词（系统指令 + 输入）与输出（AI 解析出的结构化内容），以及模型、token、耗时、报错'],
  ['搜索', '每个查询在每个引擎上的状态（成功 / 被拦截 / 无法访问 / 结果无关）与完整搜索结果（标题、链接、摘要）'],
  ['读取', '每个网页的读取方式（HTTP / 浏览器）、状态、失败原因与正文片段；上传文件的解析器与解析出的文本'],
  ['任务', '执行日志、每个步骤的输入输出与错误、搜索候选、已读来源与正文、证据、成果、对话消息、人机验证截图'],
  ['系统', '全局运行日志（含报错堆栈）、失败汇总、配置摘要、模型与智能体分工、依赖版本（不含任何密钥）'],
] as const
</script>

<template>
  <AdminPage>
    <template #actions>
      <button type="button" class="btn-secondary" @click="load(); loadTasks()"><RefreshCw class="h-3.5 w-3.5" /> 刷新</button>
    </template>

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <!-- 详细调试记录开关 -->
      <section class="ac-panel">
        <div class="ac-panel-head">
          <span class="ac-panel-title">详细调试记录</span>
          <StatusPill :tone="enabled ? 'mint' : 'gray'" :text="enabled ? '记录中' : '未开启'" />
          <div class="flex-1" />
          <ToggleSwitch :model-value="enabled" :disabled="saving" label="详细调试记录" @update:model-value="toggle" />
        </div>
        <div class="space-y-3 p-4 text-[13px] text-slate-300">
          <p>
            开启后，系统会完整记录下面这些内容，用于排查“为什么搜不到 / 为什么理解错 / 为什么报错”。基础执行日志一直都有，这里是更详细的一层。
          </p>
          <dl class="ac-dl">
            <template v-for="[k, v] in CONTENTS" :key="k">
              <dt>{{ k }}</dt>
              <dd>{{ v }}</dd>
            </template>
          </dl>
          <p class="rounded-2xl bg-[var(--pastel-butter)] px-3 py-2 text-[12px] text-[var(--pastel-butter-ink)]">
            记录里会包含提问内容、网页与文件正文，排查完建议关闭；调试记录保留 {{ status?.keep_days ?? 7 }} 天后自动删除。
          </p>
          <div class="flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-slate-400">
            <span>调试记录：{{ status?.files.length ?? 0 }} 天 · {{ formatBytes(debugBytes) }}</span>
            <span>运行日志：{{ formatBytes(status?.app_log_bytes ?? 0) }}</span>
            <span>人机验证证据：{{ status?.challenge_files ?? 0 }} 个文件</span>
          </div>
          <div class="truncate font-mono text-[11px] text-slate-500" :title="status?.logs_dir">{{ status?.logs_dir }}</div>
        </div>
      </section>

      <!-- 全系统下载 -->
      <section class="ac-panel">
        <div class="ac-panel-head">
          <span class="ac-panel-title">下载全系统日志</span>
          <span class="ac-panel-sub">时间范围内的所有任务（最多 30 个）+ 系统日志与错误汇总</span>
        </div>
        <div class="space-y-4 p-4">
          <div>
            <div class="label">时间范围</div>
            <SegmentedControl v-model="hours" small label="时间范围" :options="RANGES" />
          </div>
          <label class="flex items-center gap-2 text-[13px] text-slate-200">
            <input v-model="includeText" type="checkbox" class="h-4 w-4 accent-[var(--cs-ink)]" />
            包含网页正文与文件解析文本（文件会更大）
          </label>
          <button type="button" class="btn-primary" :disabled="busy === 'system'" @click="download()">
            <Loader2 v-if="busy === 'system'" class="h-4 w-4 animate-spin" />
            <FileArchive v-else class="h-4 w-4" />
            下载日志包（ZIP）
          </button>
          <p class="text-[12px] text-slate-500">包内 README.md 说明了每个文件的内容；把整个 ZIP 发给开发者即可分析。</p>
        </div>
      </section>
    </div>

    <!-- 按任务下载 -->
    <section class="ac-panel mt-4">
      <div class="ac-panel-head">
        <span class="ac-panel-title">按任务下载</span>
        <span class="ac-panel-sub">只包含这个任务（及其对话）的全部记录</span>
        <div class="flex-1" />
        <div class="relative w-64">
          <Search class="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <input v-model="q" class="input !pl-8" placeholder="搜索任务标题" @keydown.enter="loadTasks" />
        </div>
      </div>
      <ul>
        <li v-for="t in tasks" :key="t.task_id" class="flex items-center gap-3 border-t border-[var(--cs-line)] px-4 py-2.5 first:border-t-0">
          <Bug class="h-4 w-4 shrink-0 text-slate-500" />
          <div class="min-w-0 flex-1">
            <div class="truncate text-[13px] font-medium text-white">{{ t.title }}</div>
            <div class="text-[11px] text-slate-500">
              {{ taskStatusLabel(t.task_status, t.status_reason) }} · {{ t.display_name || t.username }} · {{ formatTime(t.created_time) }} ·
              模型调用 {{ t.llm_request_qty }} 次
            </div>
          </div>
          <button type="button" class="btn-secondary btn-sm" :disabled="busy === t.task_id" @click="download(t.task_id)">
            <Loader2 v-if="busy === t.task_id" class="h-3.5 w-3.5 animate-spin" />
            <Download v-else class="h-3.5 w-3.5" />
            下载详细日志
          </button>
        </li>
        <li v-if="!tasks.length" class="px-4 py-6 text-center text-[13px] text-slate-500">没有任务</li>
      </ul>
    </section>
  </AdminPage>
</template>
