<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowUp, BookOpen, Database, FileBarChart, Loader2, Paperclip, Search, Square, Zap } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import ModeSelect from '@/components/common/ModeSelect.vue'
import { MODE_OPTIONS } from '@/lib/format'
import { ACCEPT } from '@/lib/fileTypes'
import type { Attachment } from '@/lib/useAttachments'
import AttachmentChip from '@/components/files/AttachmentChip.vue'

const text = defineModel<string>({ required: true })
const mode = defineModel<ModeSelection>('mode', { required: true })
const props = defineProps<{
  placeholder?: string
  sending?: boolean
  disabled?: boolean
  /** 有运行中的任务时显示“停止当前轮” */
  showStop?: boolean
  stopping?: boolean
  stopHint?: string
  variant?: 'home' | 'chat'
  hint?: string | null
  /** 附件（传入即启用上传） */
  attachments?: Attachment[]
  /** 附件仍在上传：暂不能发送 */
  uploading?: boolean
}>()
const emit = defineEmits<{
  submit: []
  stop: []
  pick: [files: File[]]
  removeFile: [key: string]
  retryFile: [key: string]
  openFile: [fileId: string]
}>()
const fileInput = ref<HTMLInputElement | null>(null)
const canAttach = computed(() => props.attachments !== undefined)
const hasFiles = computed(() => (props.attachments ?? []).some((a) => a.file && a.status !== 'failed'))
const effectivePlaceholder = computed(() =>
  hasFiles.value && !text.value.trim() ? '问问这些文件…（直接发送即总结）' : props.placeholder,
)

function pickFiles() {
  fileInput.value?.click()
}
function onPicked(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) emit('pick', Array.from(input.files))
  input.value = ''
}
function onPaste(e: ClipboardEvent) {
  if (!canAttach.value) return
  const files = Array.from(e.clipboardData?.files ?? [])
  if (!files.length) return
  e.preventDefault()
  // 截图粘贴通常叫 image.png：加上时间避免重名
  emit('pick', files.map((f) => (f.name === 'image.png' ? new File([f], `截图-${Date.now()}.png`, { type: f.type }) : f)))
}

const ta = ref<HTMLTextAreaElement | null>(null)
const composing = ref(false)
const MAX_H = 240

const canSend = computed(
  () => !props.sending && !props.disabled && !props.uploading && (text.value.trim().length > 0 || hasFiles.value),
)

function autoGrow() {
  const el = ta.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, MAX_H)}px`
  el.style.overflowY = el.scrollHeight > MAX_H ? 'auto' : 'hidden'
}

watch(text, () => nextTick(autoGrow))
onMounted(autoGrow)

function onKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter') return
  // 输入法组合输入期间的回车用于确认候选词，绝不发送
  if (e.isComposing || composing.value || e.keyCode === 229) return
  if (e.shiftKey) return
  e.preventDefault()
  submit()
}

function submit() {
  if (!canSend.value) return
  emit('submit')
}

function focus() {
  ta.value?.focus()
}
defineExpose({ focus, pickFiles })

/** 对话页宽屏：彩色圆形模式按钮 */
const MODE_STYLE: Record<ModeSelection, { icon: unknown; tone: string; short: string }> = {
  auto: { icon: Zap, tone: 'butter', short: '智能' },
  quick_search: { icon: Search, tone: 'sky', short: '搜索问题' },
  research: { icon: BookOpen, tone: 'lilac', short: '深入研究' },
  dataset: { icon: Database, tone: 'mint', short: '采集数据' },
  hybrid: { icon: FileBarChart, tone: 'peach', short: '数据+报告' },
}
const MODE_BUTTONS = [...MODE_OPTIONS.filter((m) => m.value !== 'auto'), ...MODE_OPTIONS.filter((m) => m.value === 'auto')]
</script>

<template>
  <!-- 首页：单行搜索条（白底、阴影，在插画背景上保持清晰）；对话页：输入框 + 操作行 -->
  <div
    v-if="variant === 'home'"
    class="surface relative w-full rounded-[26px] px-4 py-2.5 shadow-lg transition-shadow focus-within:ring-2 focus-within:ring-brand-400/40"
  >
    <input ref="fileInput" type="file" multiple class="hidden" :accept="ACCEPT" @change="onPicked" />
    <div v-if="hint" class="mb-2 rounded-lg bg-brand-500/10 px-3 py-1.5 text-xs text-brand-300">{{ hint }}</div>
    <div v-if="attachments?.length" class="mb-2 flex flex-wrap gap-2 pt-1" aria-label="附件">
      <AttachmentChip
        v-for="a in attachments"
        :key="a.key"
        :att="a"
        @remove="emit('removeFile', a.key)"
        @retry="emit('retryFile', a.key)"
      />
    </div>
    <div class="flex items-end gap-2.5">
      <Search class="mb-2.5 h-5 w-5 shrink-0 text-slate-400" aria-hidden="true" />
      <label class="sr-only" for="cs-composer">输入需求</label>
      <textarea
        id="cs-composer"
        ref="ta"
        v-model="text"
        rows="1"
        class="block min-h-[40px] w-full resize-none bg-transparent py-2 text-[15px] leading-6 text-white placeholder:text-slate-500 focus:outline-none"
        :placeholder="effectivePlaceholder || '描述你的问题，或告诉我想采集哪些数据…'"
        :disabled="disabled"
        @keydown="onKeydown"
        @paste="onPaste"
        @compositionstart="composing = true"
        @compositionend="composing = false"
      />
      <div class="mb-1 flex shrink-0 items-center gap-2">
        <button v-if="canAttach" type="button" class="attach-btn" title="上传文件" aria-label="上传文件" :disabled="disabled" @click="pickFiles">
          <Paperclip class="h-[18px] w-[18px]" />
        </button>
        <ModeSelect v-model="mode" placement="bottom" />
        <button
          type="button"
          class="round-btn"
          :disabled="!canSend"
          aria-label="发送"
          @click="submit"
        >
          <Loader2 v-if="sending" class="h-4 w-4 animate-spin" />
          <ArrowUp v-else class="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>
  <div
    v-else
    class="composer-float @container relative w-full rounded-[28px] border p-3 pl-4 transition-shadow focus-within:ring-2 focus-within:ring-slate-400/30"
  >
    <input ref="fileInput" type="file" multiple class="hidden" :accept="ACCEPT" @change="onPicked" />
    <div v-if="hint" class="mb-2 rounded-2xl card-butter px-3 py-1.5 text-xs font-medium accent-ink">{{ hint }}</div>
    <div v-if="attachments?.length" class="-ml-1 mb-2 flex flex-wrap gap-2" aria-label="附件">
      <AttachmentChip
        v-for="a in attachments"
        :key="a.key"
        :att="a"
        @remove="emit('removeFile', a.key)"
        @retry="emit('retryFile', a.key)"
        @open="a.file && emit('openFile', a.file.file_id)"
      />
    </div>
    <label class="sr-only" for="cs-composer">输入需求</label>
    <textarea
      id="cs-composer"
      ref="ta"
      v-model="text"
      rows="1"
      class="block min-h-[28px] w-full resize-none bg-transparent px-1 pt-1 text-[16px] leading-7 text-white placeholder:text-slate-500 focus:outline-none"
      :placeholder="effectivePlaceholder || '描述你的问题，或告诉我想采集哪些数据…'"
      :disabled="disabled"
      @keydown="onKeydown"
      @paste="onPaste"
      @compositionstart="composing = true"
      @compositionend="composing = false"
    />
    <div class="mt-2.5 flex items-center gap-1.5">
      <button
        v-if="canAttach"
        type="button"
        class="attach-btn"
        title="上传文件：PDF、Word、Excel、PPT、图片、文本…（也可以拖进来或粘贴）"
        aria-label="上传文件"
        :disabled="disabled"
        @click="pickFiles"
      >
        <Paperclip class="h-[18px] w-[18px]" />
      </button>
      <!-- 宽：彩色模式按钮；窄：下拉 -->
      <div class="hidden items-center gap-1.5 @2xl:flex" role="radiogroup" aria-label="执行模式">
        <button
          v-for="m in MODE_BUTTONS"
          :key="m.value"
          type="button"
          role="radio"
          :aria-checked="mode === m.value"
          :title="m.desc"
          class="mode-btn"
          :class="mode === m.value ? 'mode-btn-on' : ''"
          @click="mode = m.value"
        >
          <span class="flex h-7 w-7 items-center justify-center rounded-full" :class="`card-${MODE_STYLE[m.value].tone} accent-ink`">
            <component :is="MODE_STYLE[m.value].icon" class="h-3.5 w-3.5" />
          </span>
          {{ MODE_STYLE[m.value].short }}
        </button>
      </div>
      <div class="@2xl:hidden"><ModeSelect v-model="mode" placement="top" /></div>
      <div class="flex-1" />
      <span v-if="!showStop" class="mr-1 hidden text-xs whitespace-nowrap text-slate-500 @2xl:inline">Enter 发送 · Shift+Enter 换行</span>
      <button
        v-if="showStop"
        type="button"
        class="btn-danger btn-sm !py-2"
        :disabled="stopping"
        :title="stopHint"
        aria-label="停止当前轮"
        @click="emit('stop')"
      >
        <Loader2 v-if="stopping" class="h-3.5 w-3.5 animate-spin" />
        <Square v-else class="h-3.5 w-3.5" />
        {{ stopping ? '正在停止…' : '停止当前轮' }}
      </button>
      <button type="button" class="round-btn" :disabled="!canSend" aria-label="发送" @click="submit">
        <Loader2 v-if="sending" class="h-4 w-4 animate-spin" />
        <ArrowUp v-else class="h-[18px] w-[18px]" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.composer-float {
  background-color: var(--cs-surface-solid);
  border-color: var(--cs-line);
  box-shadow: 0 2px 6px rgba(17, 18, 20, 0.04), 0 18px 40px -22px rgba(17, 18, 20, 0.28);
}
.attach-btn {
  display: inline-flex;
  height: 2.25rem;
  width: 2.25rem;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  color: var(--color-slate-300);
  transition: background-color 0.15s, color 0.15s;
}
.attach-btn:hover:not(:disabled) {
  background-color: var(--cs-surface-sunken);
  color: var(--color-white);
}
.attach-btn:disabled {
  opacity: 0.4;
}
.mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 9999px;
  padding: 0.2rem 0.75rem 0.2rem 0.2rem;
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
  color: var(--color-slate-300);
  border: 1px solid transparent;
  transition: background-color 0.15s, color 0.15s, border-color 0.15s;
}
.mode-btn:hover {
  background-color: color-mix(in srgb, var(--color-white) 5%, transparent);
  color: var(--color-white);
}
.mode-btn-on,
.mode-btn-on:hover {
  background-color: var(--cs-surface-sunken);
  border-color: var(--cs-line-strong);
  color: var(--color-white);
}
</style>
