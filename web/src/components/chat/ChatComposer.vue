<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowUp, Loader2, Search, Square } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import ModeSelect from '@/components/common/ModeSelect.vue'

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
}>()
const emit = defineEmits<{ submit: []; stop: [] }>()

const ta = ref<HTMLTextAreaElement | null>(null)
const composing = ref(false)
const MAX_H = 240

const canSend = computed(() => !props.sending && !props.disabled && text.value.trim().length > 0)

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
defineExpose({ focus })
</script>

<template>
  <!-- 首页：单行搜索条（白底、阴影，在插画背景上保持清晰）；对话页：输入框 + 操作行 -->
  <div
    v-if="variant === 'home'"
    class="surface relative w-full rounded-[26px] px-4 py-2.5 shadow-lg transition-shadow focus-within:ring-2 focus-within:ring-brand-400/40"
  >
    <div v-if="hint" class="mb-2 rounded-lg bg-brand-500/10 px-3 py-1.5 text-xs text-brand-300">{{ hint }}</div>
    <div class="flex items-end gap-2.5">
      <Search class="mb-2.5 h-5 w-5 shrink-0 text-slate-400" aria-hidden="true" />
      <label class="sr-only" for="cs-composer">输入需求</label>
      <textarea
        id="cs-composer"
        ref="ta"
        v-model="text"
        rows="1"
        class="block min-h-[40px] w-full resize-none bg-transparent py-2 text-[15px] leading-6 text-white placeholder:text-slate-500 focus:outline-none"
        :placeholder="placeholder || '描述你的问题，或告诉我想采集哪些数据…'"
        :disabled="disabled"
        @keydown="onKeydown"
        @compositionstart="composing = true"
        @compositionend="composing = false"
      />
      <div class="mb-1 flex shrink-0 items-center gap-2">
        <ModeSelect v-model="mode" placement="bottom" />
        <button
          type="button"
          class="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-b from-brand-500 to-brand-600 text-snow shadow-md shadow-brand-600/30 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
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
    class="surface relative w-full rounded-2xl p-3 transition-shadow focus-within:ring-2 focus-within:ring-brand-400/30"
  >
    <div v-if="hint" class="mb-2 rounded-lg bg-brand-500/10 px-3 py-1.5 text-xs text-brand-300">{{ hint }}</div>
    <label class="sr-only" for="cs-composer">输入需求</label>
    <textarea
      id="cs-composer"
      ref="ta"
      v-model="text"
      rows="1"
      class="block min-h-[24px] w-full resize-none bg-transparent px-1 text-[15px] leading-6 text-white placeholder:text-slate-500 focus:outline-none"
      :placeholder="placeholder || '描述你的问题，或告诉我想采集哪些数据…'"
      :disabled="disabled"
      @keydown="onKeydown"
      @compositionstart="composing = true"
      @compositionend="composing = false"
    />
    <div class="mt-2 flex items-center gap-2">
      <ModeSelect v-model="mode" placement="top" />
      <span class="hidden text-xs text-slate-500 sm:inline">Enter 发送 · Shift+Enter 换行</span>
      <div class="flex-1" />
      <button
        v-if="showStop"
        type="button"
        class="btn-danger btn-sm"
        :disabled="stopping"
        :title="stopHint"
        aria-label="停止当前轮"
        @click="emit('stop')"
      >
        <Loader2 v-if="stopping" class="h-3.5 w-3.5 animate-spin" />
        <Square v-else class="h-3.5 w-3.5" />
        {{ stopping ? '正在停止…' : '停止当前轮' }}
      </button>
      <button
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-b from-brand-500 to-brand-600 text-snow shadow-md shadow-brand-600/30 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="!canSend"
        aria-label="发送"
        @click="submit"
      >
        <Loader2 v-if="sending" class="h-4 w-4 animate-spin" />
        <ArrowUp v-else class="h-4 w-4" />
      </button>
    </div>
  </div>
</template>
