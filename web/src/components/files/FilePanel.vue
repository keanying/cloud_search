<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { AlertTriangle, Download, ListTree, Loader2, RotateCw } from 'lucide-vue-next'
import type { FileContentOut, FileOut } from '@/api/types'
import { api } from '@/api/client'
import { renderMarkdownPlain } from '@/lib/markdown'
import { MINERU_HINT, formatSize, parserShort } from '@/lib/fileTypes'
import { useChatStore } from '@/stores/chat'
import { useToastStore } from '@/stores/toast'
import FileTypeIcon from './FileTypeIcon.vue'

/** 右侧面板：上传文件的解析结果预览（大纲 + Markdown 正文） */
const props = defineProps<{ fileId: string | null }>()
const chat = useChatStore()
const toast = useToastStore()
const file = ref<FileOut | null>(null)
const content = ref<FileContentOut | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const busy = ref(false)
const body = ref<HTMLElement | null>(null)
const showOutline = ref(true)

const html = computed(() => (content.value ? renderMarkdownPlain(content.value.markdown) : ''))
const parsing = computed(() => file.value?.parse_status === 'queued' || file.value?.parse_status === 'parsing')
const needsMineru = computed(() => {
  const err = file.value?.parse_error || ''
  if (/mineru\.(api_url|cloud_token)/.test(err)) return false // 错误说明里已经写了怎么配置
  return /MinerU|扫描|图片|png|jpe?g|ppt|webp|bmp|tiff?/i.test(err + ' ' + (file.value?.ext || ''))
})
const mentionsConfig = computed(() => /mineru\.(api_url|cloud_token)/.test(file.value?.parse_error || ''))
const stats = computed(() => {
  const f = file.value
  if (!f) return []
  return [
    f.page_qty ? `${f.page_qty} 页` : '',
    f.table_qty ? `${f.table_qty} 个表格` : '',
    f.image_qty ? `${f.image_qty} 张图片` : '',
    f.char_qty ? (f.char_qty < 10000 ? `${f.char_qty} 字` : `${(f.char_qty / 10000).toFixed(f.char_qty < 100000 ? 1 : 0)} 万字`) : '',
    formatSize(f.byte_qty),
  ].filter(Boolean)
})

async function load(id: string) {
  loading.value = true
  error.value = null
  try {
    const f = await api.getFile(id)
    if (props.fileId !== id) return
    file.value = f
    content.value = f.parse_status === 'parsed' ? await api.fileContent(id) : null
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.fileId,
  (id) => {
    file.value = null
    content.value = null
    if (id) void load(id)
  },
  { immediate: true },
)
// 解析状态由会话事件推送：解析完成后加载正文
watch(
  () => (props.fileId ? chat.files[props.fileId]?.parse_status : null),
  (st, before) => {
    if (!props.fileId || !st || st === before) return
    if (file.value && st !== file.value.parse_status) void load(props.fileId)
  },
)

async function download() {
  if (!file.value) return
  try {
    await api.downloadFile(file.value.file_id, file.value.name)
  } catch (e) {
    toast.error(e, '下载失败')
  }
}

async function reparse() {
  if (!file.value) return
  busy.value = true
  try {
    file.value = await api.reparseFile(file.value.file_id)
    content.value = null
    toast.push('已重新加入解析队列', 'info')
  } catch (e) {
    toast.error(e, '重新解析失败')
  } finally {
    busy.value = false
  }
}

async function jump(item: string) {
  await nextTick()
  const want = item.trim()
  const el = Array.from(body.value?.querySelectorAll('h1,h2,h3,h4,h5') ?? []).find((h) => h.textContent?.trim() === want)
  el?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}
</script>

<template>
  <div class="flex h-full flex-col">
    <div v-if="loading && !file" class="flex flex-1 items-center justify-center text-sm text-slate-400">
      <Loader2 class="mr-2 h-4 w-4 animate-spin" /> 正在加载文件…
    </div>
    <div v-else-if="error" class="p-4 text-sm text-rose-300">{{ error }}</div>
    <template v-else-if="file">
      <header class="hairline border-b px-4 py-3">
        <div class="flex items-start gap-3">
          <FileTypeIcon :ext="file.ext" />
          <div class="min-w-0 flex-1">
            <h3 class="truncate text-[15px] font-bold text-white" :title="file.name">{{ file.name }}</h3>
            <div class="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
              <span v-if="file.parse_status === 'parsed'" class="pill card-mint accent-ink" :title="file.parse_detail || ''">
                {{ file.parse_detail || parserShort(file.parser) }}
              </span>
              <span v-else-if="parsing" class="pill card-butter accent-ink"><Loader2 class="h-3 w-3 animate-spin" /> {{ file.parse_status_label }}</span>
              <span v-else class="pill card-peach accent-ink">解析失败</span>
              <span v-for="s in stats" :key="s">{{ s }}</span>
            </div>
          </div>
          <div class="flex shrink-0 gap-1.5">
            <button v-if="file.parse_status === 'failed'" class="btn-primary btn-sm" :disabled="busy" @click="reparse">
              <RotateCw class="h-3.5 w-3.5" :class="busy ? 'animate-spin' : ''" /> 重新解析
            </button>
            <button class="btn-secondary btn-sm" title="下载原文件" @click="download"><Download class="h-3.5 w-3.5" /> 原文件</button>
          </div>
        </div>
      </header>

      <div v-if="parsing" class="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-400">
        <Loader2 class="h-6 w-6 animate-spin" />
        <div class="font-semibold text-white">正在解析…</div>
        <div>大文件、扫描件用 MinerU 识别可能需要几分钟；解析完成后会自动显示。<br />现在就可以提问，回答会等文件解析完再开始。</div>
      </div>

      <div v-else-if="file.parse_status === 'failed'" class="p-4">
        <div class="card-peach rounded-2xl p-4 accent-ink">
          <div class="flex items-center gap-2 font-bold"><AlertTriangle class="h-4 w-4" /> 没能读取这个文件</div>
          <p class="mt-2 text-sm leading-6">{{ file.parse_error || '未知原因' }}</p>
          <p v-if="needsMineru" class="mt-2 text-sm leading-6 opacity-90">{{ MINERU_HINT }}。配置好后点「重新解析」。</p>
          <p v-else-if="mentionsConfig" class="mt-2 text-sm leading-6 opacity-90">配置好后点「重新解析」即可，不需要重新上传。</p>
          <p v-else class="mt-2 text-sm leading-6 opacity-90">可以换成 PDF / Word / Excel 等格式重新上传，或稍后重试。</p>
        </div>
      </div>

      <div v-else class="min-h-0 flex-1 overflow-y-auto">
        <section v-if="file.outline.length" class="hairline mx-4 mt-4 rounded-2xl border p-3">
          <button class="flex w-full items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white" :aria-expanded="showOutline" @click="showOutline = !showOutline">
            <ListTree class="h-3.5 w-3.5" /> 大纲（{{ file.outline.length }}）
          </button>
          <ol v-if="showOutline" class="mt-2 max-h-56 space-y-0.5 overflow-y-auto text-[13px]">
            <li v-for="(o, i) in file.outline" :key="i">
              <button
                class="w-full truncate rounded-lg px-2 py-1 text-left text-slate-200 hover:bg-[var(--cs-line)] hover:text-white"
                :style="{ paddingLeft: `${8 + (o.length - o.trimStart().length) * 6}px` }"
                @click="jump(o)"
              >
                {{ o.trim() }}
              </button>
            </li>
          </ol>
        </section>
        <p v-if="content?.truncated" class="mx-4 mt-3 text-xs text-slate-400">内容较长，预览只显示前 30 万字；回答时会读取全文。</p>
        <!-- eslint-disable-next-line vue/no-v-html -- markdown-it(html:false) + DOMPurify 净化 -->
        <article ref="body" class="prose-cs px-5 py-4 text-[14.5px]" v-html="html" />
      </div>
    </template>
  </div>
</template>
