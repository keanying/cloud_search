<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { MessageSquare } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import { api } from '@/api/client'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import { HOME_ACTIONS, runHomeAction, visibleActions, type HomeAction } from '@/lib/homeActions'
import { relativeTime } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useConversationsStore } from '@/stores/conversations'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const chat = useChatStore()
const convs = useConversationsStore()
const panel = usePanelStore()
const toast = useToastStore()
const ui = useUiStore()

const text = ref('')
const mode = ref<ModeSelection>((localStorage.getItem('cs_default_mode') as ModeSelection) || 'auto')
const sending = ref(false)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)

const shortcuts = computed(() => visibleActions(!!auth.user?.is_admin, 'home'))

/** 模式快捷入口只切换模式并预填示例文字，不会自动发送 */
function applyMode(m: ModeSelection) {
  const a = HOME_ACTIONS.find((x) => x.mode === m)
  mode.value = m
  if (a?.example && !text.value.trim()) text.value = a.example
  composer.value?.focus()
}

function onShortcut(a: HomeAction) {
  if (a.mode) applyMode(a.mode)
  else runHomeAction(a, router, () => ui.openHistory())
}

// 从应用启动器跳转过来：/?mode=research&prefill=1
watch(
  () => route.query,
  (q) => {
    const m = q.mode as ModeSelection | undefined
    if (m && HOME_ACTIONS.some((a) => a.mode === m)) {
      applyMode(m)
      void router.replace({ name: 'home' })
    }
  },
  { immediate: true },
)

// 右下角时钟
const now = ref(new Date())
let timer: number | undefined
const clock = computed(() => now.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }))
const dateLabel = computed(() => {
  const d = now.value
  const week = '日一二三四五六'[d.getDay()]
  return `${d.getMonth() + 1}月${d.getDate()}日 星期${week}`
})

onMounted(() => {
  chat.close()
  panel.reset()
  void convs.refresh().catch(() => {})
  timer = window.setInterval(() => (now.value = new Date()), 15_000)
})
onBeforeUnmount(() => window.clearInterval(timer))

async function submit() {
  const t = text.value.trim()
  if (!t || sending.value) return
  sending.value = true
  try {
    const conv = await api.createConversation()
    convs.upsert(conv)
    await chat.open(conv.conversation_id)
    await chat.send(t, mode.value)
    text.value = ''
    router.push({ name: 'chat', params: { id: conv.conversation_id } })
  } catch (e) {
    // 发送失败时保留输入内容，不显示伪成功
    toast.error(e, '发送失败，输入内容已保留')
  } finally {
    sending.value = false
  }
}

const last = computed(() => convs.items.find((c) => c.conversation_status === 'active') ?? null)
</script>

<template>
  <div class="relative h-full overflow-y-auto">
    <div class="mx-auto flex min-h-full max-w-4xl flex-col items-center justify-center px-4 pt-6 pb-28">
      <h1 class="text-center text-2xl font-medium tracking-wide text-white md:text-[28px]">你好，今天想探索什么？</h1>
      <p class="mt-2 text-center text-sm text-slate-400">从一个问题开始，让 AI 帮你搜索、整理数据、生成报告</p>

      <div class="mt-7 w-full max-w-[720px]">
        <ChatComposer
          ref="composer"
          v-model="text"
          v-model:mode="mode"
          variant="home"
          :sending="sending"
          placeholder="搜索问题，或描述想采集的数据、想要的报告…"
          @submit="submit"
        />
      </div>

      <nav class="mt-8 flex max-w-[720px] flex-wrap justify-center gap-x-5 gap-y-4" aria-label="快捷入口">
        <button
          v-for="a in shortcuts"
          :key="a.key"
          type="button"
          class="group flex w-[76px] flex-col items-center gap-2 rounded-xl py-1 text-xs text-slate-200"
          :title="a.mode ? `${a.label}：切换模式并填入示例` : a.label"
          @click="onShortcut(a)"
        >
          <span
            class="surface flex h-12 w-12 items-center justify-center rounded-full transition group-hover:-translate-y-0.5 group-hover:shadow-lg"
            :class="mode === a.mode ? 'ring-2 ring-brand-400' : ''"
          >
            <component :is="a.icon" class="h-5 w-5" :class="a.color" />
          </span>
          <span class="rounded px-1">{{ a.label }}</span>
        </button>
      </nav>
    </div>

    <!-- 左下：最近一次对话；右下：时钟与日期（窄屏隐藏） -->
    <div class="pointer-events-none absolute inset-x-0 bottom-0 hidden items-end justify-between p-5 md:flex">
      <RouterLink
        v-if="last"
        :to="{ name: 'chat', params: { id: last.conversation_id } }"
        class="glass pointer-events-auto flex max-w-[280px] items-center gap-3 px-3.5 py-2.5 hover:shadow-lg"
      >
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-500/12">
          <MessageSquare class="h-4 w-4 text-brand-300" />
        </span>
        <span class="min-w-0">
          <span class="block truncate text-sm font-medium text-white">{{ last.title }}</span>
          <span class="block text-[11px] text-slate-400">{{ relativeTime(last.updated_time) }}<template v-if="last.active_task_qty"> · 进行中</template></span>
        </span>
      </RouterLink>
      <div v-else-if="convs.loaded" class="glass pointer-events-auto px-3.5 py-2.5 text-xs text-slate-400">还没有对话</div>
      <span v-else />
      <div class="glass pointer-events-auto px-4 py-2 text-right">
        <div class="text-2xl leading-8 font-light tracking-wide text-white tabular-nums">{{ clock }}</div>
        <div class="text-[11px] tracking-wider text-slate-400">{{ dateLabel }}</div>
      </div>
    </div>
  </div>
</template>
