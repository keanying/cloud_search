<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ChevronDown, MessageSquare } from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import { api } from '@/api/client'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import HomeArtLayer from '@/components/home/art/HomeArtLayer.vue'
import { HOME_ACTIONS, runHomeAction, visibleActions, type HomeAction } from '@/lib/homeActions'
import { relativeTime } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useConversationsStore } from '@/stores/conversations'
import { usePanelStore } from '@/stores/panel'
import { usePrefsStore } from '@/stores/prefs'
import { useToastStore } from '@/stores/toast'
import { useUiStore } from '@/stores/ui'
import { useAttachments } from '@/lib/useAttachments'

// 首屏之下的产品介绍单独成包，首屏搜索框立即可用
const LandingSections = defineAsyncComponent(() => import('@/components/landing/LandingSections.vue'))

const DRAFT_KEY = 'cs_home_draft'
const SECTION_IDS = ['features', 'how', 'scenarios', 'security', 'faq']

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const chat = useChatStore()
const convs = useConversationsStore()
const panel = usePanelStore()
const prefs = usePrefsStore()
const toast = useToastStore()
const ui = useUiStore()

const text = ref('')
const mode = ref<ModeSelection>((localStorage.getItem('cs_default_mode') as ModeSelection) || 'auto')
const sending = ref(false)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
const scroller = ref<HTMLElement | null>(null)
const hero = ref<HTMLElement | null>(null)

const loggedIn = computed(() => !!auth.user)

// 首页附件：第一次上传时先建好对话（发送时沿用这个对话）
const homeConvId = ref<string | null>(null)
async function ensureConversation(): Promise<string> {
  if (!homeConvId.value) {
    const conv = await api.createConversation()
    convs.upsert(conv)
    homeConvId.value = conv.conversation_id
  }
  return homeConvId.value
}
const attachments = useAttachments(ensureConversation)
// 未登录访客只显示模式类快捷入口（最近对话/成果需要登录）
const shortcuts = computed(() =>
  visibleActions(!!auth.user?.is_admin, 'home').filter((a) => loggedIn.value || !!a.mode),
)

/** 模式快捷入口只切换模式并预填示例文字，不会自动发送 */
function applyMode(m: ModeSelection, example?: string) {
  const a = HOME_ACTIONS.find((x) => x.mode === m)
  mode.value = m
  if (example) text.value = example
  else if (a?.example && !text.value.trim()) text.value = a.example
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

// ---------------------------------------------------------------- 滚动：顶栏状态与导航高亮
let raf = 0
function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    const el = scroller.value
    if (!el) return
    const heroH = hero.value?.offsetHeight ?? window.innerHeight
    ui.landingScrolled = el.scrollTop > heroH - 72
    let active = ''
    for (const id of SECTION_IDS) {
      const s = document.getElementById(id)
      if (s && s.getBoundingClientRect().top <= 140) active = id
    }
    ui.activeSection = active
  })
}

function smooth(): ScrollBehavior {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

function scrollToIntro() {
  document.getElementById('intro')?.scrollIntoView({ behavior: smooth(), block: 'start' })
}

/** 回到首屏并聚焦搜索框（介绍区的「从一个问题开始」「试试这个」） */
async function backToSearch(m?: ModeSelection, example?: string) {
  scroller.value?.scrollTo({ top: 0, behavior: smooth() })
  await nextTick()
  if (m) applyMode(m, example)
  window.setTimeout(() => composer.value?.focus(), 350)
}

onMounted(() => {
  chat.close()
  panel.reset()
  if (loggedIn.value) void convs.refresh().catch(() => {})
  timer = window.setInterval(() => (now.value = new Date()), 15_000)
  // 登录前填写的问题：登录后恢复到输入框（不自动发送）
  if (loggedIn.value) {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    if (raw) {
      sessionStorage.removeItem(DRAFT_KEY)
      try {
        const d = JSON.parse(raw) as { text: string; mode: ModeSelection }
        text.value = d.text
        mode.value = d.mode
        toast.push('已恢复登录前输入的问题，确认后发送即可', 'info')
        void nextTick(() => composer.value?.focus())
      } catch {
        /* 忽略损坏的草稿 */
      }
    }
  }
  onScroll()
})
onBeforeUnmount(() => {
  window.clearInterval(timer)
  ui.landingScrolled = false
  ui.activeSection = ''
})

async function submit() {
  const t = text.value.trim()
  const fileIds = attachments.fileIds.value
  if ((!t && !fileIds.length) || sending.value || attachments.uploading.value) return
  if (!loggedIn.value) {
    // 未登录：保存草稿，登录/注册后回到首页恢复
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ text: t, mode: mode.value }))
    void router.push({ name: 'login', query: { redirect: '/' } })
    return
  }
  sending.value = true
  try {
    const cid = await ensureConversation()
    await chat.open(cid)
    await chat.send(t, mode.value, fileIds)
    text.value = ''
    attachments.clear()
    homeConvId.value = null
    router.push({ name: 'chat', params: { id: cid } })
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
  <div ref="scroller" class="relative h-full overflow-y-auto" @scroll.passive="onScroll">
    <!-- 首屏：搜索 -->
    <section ref="hero" class="relative flex min-h-[100dvh] flex-col" aria-label="搜索">
      <HomeArtLayer :art="prefs.homeArt" />
      <div class="relative mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-4 pt-20 pb-32">
        <h1 class="text-center text-[28px] font-bold tracking-tight text-white md:text-[36px]">你好，今天想探索什么？</h1>
        <p class="mt-2 text-center text-sm text-slate-400">从一个问题开始，让 AI 帮你搜索、整理数据、生成报告</p>

        <div class="mt-7 w-full max-w-[720px]">
          <ChatComposer
            ref="composer"
            v-model="text"
            v-model:mode="mode"
            variant="home"
            :sending="sending"
            placeholder="搜索问题，或描述想采集的数据、想要的报告…"
            :attachments="loggedIn ? attachments.items.value : undefined"
            :uploading="attachments.uploading.value"
            @submit="submit"
            @pick="attachments.add"
            @remove-file="attachments.remove"
            @retry-file="attachments.retry"
          />
          <p v-if="!loggedIn" class="mt-2 text-center text-xs text-slate-500">登录后即可发送，输入的内容会为你保留</p>
        </div>

        <nav class="mt-8 flex max-w-[720px] flex-wrap justify-center gap-x-2 gap-y-4 sm:gap-x-5" aria-label="快捷入口">
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

      <!-- 向下了解更多 -->
      <button
        type="button"
        class="glass absolute bottom-6 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full py-1.5 pr-3 pl-4 text-xs text-slate-300 transition hover:text-white"
        aria-label="向下了解更多"
        @click="scrollToIntro"
      >
        <span>向下了解更多</span>
        <ChevronDown class="lp-bounce h-4 w-4" />
      </button>

      <!-- 左下：最近一次对话（登录后）；右下：时钟与日期（窄屏隐藏） -->
      <div class="pointer-events-none absolute inset-x-0 bottom-0 hidden items-end justify-between p-5 md:flex">
        <RouterLink
          v-if="loggedIn && last"
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
        <div v-else-if="loggedIn && convs.loaded" class="glass pointer-events-auto px-3.5 py-2.5 text-xs text-slate-400">还没有对话</div>
        <span v-else />
        <div class="glass pointer-events-auto px-4 py-2 text-right">
          <div class="text-2xl leading-8 font-light tracking-wide text-white tabular-nums">{{ clock }}</div>
          <div class="text-[11px] tracking-wider text-slate-400">{{ dateLabel }}</div>
        </div>
      </div>
    </section>

    <!-- 首屏之下：产品介绍、亮点、场景等 -->
    <LandingSections :logged-in="loggedIn" @try="(m: ModeSelection, t: string) => backToSearch(m, t)" @start="backToSearch()" />
  </div>
</template>
