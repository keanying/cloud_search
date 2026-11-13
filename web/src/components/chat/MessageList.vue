<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { ArrowDown } from 'lucide-vue-next'
import type { MessageOut } from '@/api/types'
import MessageItem from './MessageItem.vue'

const props = defineProps<{ messages: MessageOut[] }>()
const scroller = ref<HTMLElement | null>(null)
const atBottom = ref(true)
const hasNew = ref(false)
const THRESHOLD = 80

function checkBottom() {
  const el = scroller.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < THRESHOLD
  if (atBottom.value) hasNew.value = false
}

function scrollToBottom(smooth = true) {
  const el = scroller.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  hasNew.value = false
}

// 只有用户停留在底部时才自动跟随；否则提示“跳至最新”，不打断阅读位置
watch(
  () => props.messages.map((m) => `${m.message_id}:${m.updated_time}:${m.parts.length}`).join('|'),
  async () => {
    const follow = atBottom.value
    await nextTick()
    if (follow) scrollToBottom(false)
    else hasNew.value = true
  },
)

onMounted(() => nextTick(() => scrollToBottom(false)))
defineExpose({ scrollToBottom })
</script>

<template>
  <div class="relative min-h-0 flex-1">
    <div ref="scroller" class="h-full overflow-y-auto" @scroll.passive="checkBottom">
      <div class="mx-auto flex max-w-[860px] flex-col gap-7 px-4 pt-4 pb-8 md:px-6" role="log" aria-label="对话消息">
        <MessageItem
          v-for="(m, i) in messages"
          :key="m.message_id"
          :message="m"
          :latest="i === messages.length - 1"
        />
      </div>
    </div>
    <button
      v-if="!atBottom"
      class="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full bg-[var(--cs-ink)] px-3.5 py-2 text-xs font-semibold text-[var(--cs-on-ink)] shadow-lg"
      @click="scrollToBottom()"
    >
      <ArrowDown class="h-3.5 w-3.5" /> {{ hasNew ? '有新内容 · 跳至最新' : '跳至最新' }}
    </button>
  </div>
</template>
