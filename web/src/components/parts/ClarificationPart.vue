<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { Check, MessageCircleQuestion, PenLine, Send } from 'lucide-vue-next'
import type { ClarificationPart } from '@/api/types'
import { useChatActions } from '@/lib/chatActions'

/** 澄清：每个问题给出候选选项（单选/多选），另有“其他”可自由输入；一次提交为一条回复。 */
const props = defineProps<{ part: ClarificationPart }>()
const actions = useChatActions()

const items = computed(() =>
  props.part.items?.length
    ? props.part.items
    : props.part.questions.map((q) => ({ question: q, options: [] as string[], multi: false })),
)
const state = reactive(
  items.value.map((it) => ({ picked: [] as string[], other: it.options.length === 0, otherText: '' })),
)
const sent = ref(false)
const otherInputs = ref<HTMLInputElement[]>([])

function toggle(i: number, opt: string) {
  if (sent.value) return
  const st = state[i]
  const multi = items.value[i].multi
  if (st.picked.includes(opt)) st.picked = st.picked.filter((x) => x !== opt)
  else st.picked = multi ? [...st.picked, opt] : [opt]
  if (!multi) st.other = false
}
async function toggleOther(i: number) {
  if (sent.value) return
  const st = state[i]
  st.other = !st.other
  if (st.other && !items.value[i].multi) st.picked = []
  if (st.other) {
    await nextTick()
    otherInputs.value[i]?.focus()
  }
}
function answerOf(i: number): string {
  const st = state[i]
  const bits = [...st.picked]
  if (st.other && st.otherText.trim()) bits.push(st.otherText.trim())
  return bits.join('、')
}
const answered = computed(() => items.value.map((_, i) => answerOf(i)).filter(Boolean).length)

function submit() {
  if (sent.value || !answered.value) return
  const lines = items.value.map((it, i) => `${i + 1}. ${it.question} —— ${answerOf(i) || '没有特别要求，按常见情况'}`)
  sent.value = true
  actions.ask(lines.join('\n'))
}
function useDefaults() {
  if (sent.value) return
  sent.value = true
  actions.ask('以上问题都按常见情况处理，直接开始吧')
}
</script>

<template>
  <div class="surface p-5">
    <div class="flex items-center gap-2">
      <span class="flex h-9 w-9 items-center justify-center rounded-full card-butter">
        <MessageCircleQuestion class="h-4 w-4 accent-ink" />
      </span>
      <span class="card-title">需要你补充几点</span>
      <span class="pill card-butter accent-ink ml-auto">{{ sent ? '✓ 已回复' : '✋ 需要你' }}</span>
    </div>

    <ol class="mt-4 space-y-4">
      <li v-for="(it, i) in items" :key="i">
        <div class="flex items-start gap-2.5 text-sm font-medium text-slate-100">
          <span class="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--cs-ink)] text-[11px] font-bold text-[var(--cs-on-ink)]">{{ i + 1 }}</span>
          <span>{{ it.question }}<span v-if="it.multi" class="ml-1.5 text-xs font-normal text-slate-500">（可多选）</span></span>
        </div>
        <div class="mt-2 flex flex-wrap gap-1.5 pl-7.5" role="group" :aria-label="it.question">
          <button
            v-for="opt in it.options"
            :key="opt"
            type="button"
            class="opt"
            :class="state[i].picked.includes(opt) ? 'opt-on' : ''"
            :aria-pressed="state[i].picked.includes(opt)"
            :disabled="sent"
            @click="toggle(i, opt)"
          >
            <Check v-if="state[i].picked.includes(opt)" class="h-3.5 w-3.5" stroke-width="3" />
            {{ opt }}
          </button>
          <button
            type="button"
            class="opt"
            :class="state[i].other ? 'opt-on' : ''"
            :aria-pressed="state[i].other"
            :disabled="sent"
            @click="toggleOther(i)"
          >
            <PenLine class="h-3.5 w-3.5" /> {{ it.options.length ? '其他' : '填写回答' }}
          </button>
        </div>
        <input
          v-if="state[i].other"
          :ref="(el) => (otherInputs[i] = el as HTMLInputElement)"
          v-model="state[i].otherText"
          class="input mt-2 ml-7.5 !w-[calc(100%-1.875rem)] !py-2"
          :placeholder="it.options.length ? '写下你的情况…' : '你的回答…'"
          :disabled="sent"
          @keydown.enter.prevent="submit"
        />
      </li>
    </ol>

    <div class="mt-5 flex flex-wrap items-center gap-2">
      <button class="btn-primary btn-sm" :disabled="sent || !answered" @click="submit">
        <Send class="h-3.5 w-3.5" /> {{ sent ? '已发送' : `发送回答${answered ? `（${answered}/${items.length}）` : ''}` }}
      </button>
      <button v-if="!sent" class="btn-ghost btn-sm" @click="useDefaults">都按常见情况，直接开始</button>
      <span v-if="!sent && answered && answered < items.length" class="text-xs text-slate-500">未选的按常见情况处理</span>
    </div>
  </div>
</template>

<style scoped>
.opt {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border-radius: 999px;
  border: 1px solid var(--cs-line-strong);
  background: var(--cs-surface-solid);
  padding: 0.35rem 0.85rem;
  font-size: 13px;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}
.opt:hover:not(:disabled) {
  border-color: var(--cs-ink);
}
.opt-on {
  background: var(--cs-ink);
  border-color: var(--cs-ink);
  color: var(--cs-on-ink);
}
.opt:disabled {
  cursor: default;
  opacity: 0.75;
}
</style>
