<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { ArrowLeftToLine, ChevronDown, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Search, Sun, X } from 'lucide-vue-next'
import BrandLogo from '@/components/common/BrandLogo.vue'
import CommandPalette from '@/components/admin/CommandPalette.vue'
import { ADMIN_NAV, findAdminItem } from '@/lib/adminNav'
import { useFloating } from '@/lib/useFloating'
import { MEDIUM_QUERY, useMedia } from '@/lib/useMedia'
import { useAuthStore } from '@/stores/auth'
import { usePrefsStore } from '@/stores/prefs'
import { useUiStore } from '@/stores/ui'
import '@/styles/admin.css'

/**
 * 管理后台（控制台）布局：
 * 左侧贴边深色导航（232px，可收起为 64px 图标栏；<1024px 为抽屉）；
 * 右侧顶部 56px 工具栏（面包屑 · 命令面板 · 主题 · 用户菜单）+ 内容区。
 */
const auth = useAuthStore()
const prefs = usePrefsStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const desktop = useMedia(MEDIUM_QUERY)

// 控制台样式层只在后台生效
onMounted(() => document.documentElement.classList.add('admin-mode'))
onBeforeUnmount(() => document.documentElement.classList.remove('admin-mode'))

const KEY = 'cs_admin_collapsed'
const collapsed = ref(localStorage.getItem(KEY) === '1')
watch(collapsed, (v) => localStorage.setItem(KEY, v ? '1' : '0'))
const drawer = ref(false)
watch(() => route.fullPath, () => (drawer.value = false))
const mini = computed(() => desktop.value && collapsed.value)

const current = computed(() => findAdminItem(route.name))
const initial = computed(() => (auth.displayName || 'U').slice(0, 1).toUpperCase())
const appTarget = computed(() => (ui.lastChatId ? { name: 'chat', params: { id: ui.lastChatId } } : { name: 'home' }))
const isMac = /Mac|iPhone|iPad/.test(navigator.platform)

// 命令面板
const palette = ref(false)
function onKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    palette.value = !palette.value
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

// 用户菜单
const userOpen = ref(false)
const userAnchor = ref<HTMLElement | null>(null)
const userMenu = ref<HTMLElement | null>(null)
const { style: userStyle } = useFloating(userAnchor, userMenu, userOpen, () => 'bottom-end')
function logout() {
  userOpen.value = false
  auth.logout()
  void router.push({ name: 'login' })
}
</script>

<template>
  <div class="ac-root flex h-full">
    <div v-if="!desktop && drawer" class="fixed inset-0 z-[70] bg-black/40" @click="drawer = false" />

    <aside
      class="ac-side z-[80] flex shrink-0 flex-col"
      :class="[
        desktop ? 'relative h-full' : 'fixed inset-y-0 left-0 transition-transform duration-200',
        !desktop && !drawer ? '-translate-x-full' : '',
        mini ? 'w-16' : 'w-[232px]',
      ]"
      aria-label="管理后台导航"
    >
      <div class="flex h-14 shrink-0 items-center gap-2.5 px-4" :class="mini ? 'justify-center !px-0' : ''">
        <BrandLogo :size="28" />
        <div v-if="!mini" class="min-w-0 flex-1 leading-tight">
          <div class="text-[14px] font-bold tracking-tight">云搜浏览器</div>
          <div class="text-[11px] opacity-50">管理后台</div>
        </div>
        <button v-if="!desktop" type="button" class="side-btn" aria-label="关闭导航" @click="drawer = false"><X class="h-4 w-4" /></button>
      </div>

      <nav class="min-h-0 flex-1 overflow-y-auto px-2.5 pt-2 pb-3">
        <div v-for="(g, gi) in ADMIN_NAV" :key="gi" class="mt-4 first:mt-0">
          <div v-if="g.group && !mini" class="mb-1 px-2.5 text-[11px] font-medium opacity-40">{{ g.group }}</div>
          <div v-else-if="g.group" class="mx-auto my-2 h-px w-6 bg-white/10" />
          <RouterLink
            v-for="it in g.items"
            :key="it.name"
            :to="{ name: it.name }"
            class="side-link"
            :class="[route.name === it.name ? 'side-link-on' : '', mini ? 'justify-center !px-0' : '']"
            :title="mini ? it.label : undefined"
            :aria-current="route.name === it.name ? 'page' : undefined"
          >
            <component :is="it.icon" class="h-4 w-4 shrink-0" />
            <span v-if="!mini" class="truncate">{{ it.label }}</span>
          </RouterLink>
        </div>
      </nav>

      <div class="border-t border-white/[0.07] px-2.5 py-2.5">
        <RouterLink :to="appTarget" class="side-link" :class="mini ? 'justify-center !px-0' : ''" :title="mini ? '返回应用' : undefined">
          <ArrowLeftToLine class="h-4 w-4 shrink-0" />
          <span v-if="!mini">返回应用</span>
        </RouterLink>
        <button
          v-if="desktop"
          type="button"
          class="side-link w-full"
          :class="mini ? 'justify-center !px-0' : ''"
          :title="mini ? '展开导航' : '收起导航'"
          @click="collapsed = !collapsed"
        >
          <PanelLeftOpen v-if="mini" class="h-4 w-4" />
          <template v-else><PanelLeftClose class="h-4 w-4" /><span>收起导航</span></template>
        </button>
      </div>
    </aside>

    <div class="flex min-w-0 flex-1 flex-col">
      <header class="ac-top sticky top-0 z-40 flex h-14 shrink-0 items-center gap-3 px-4 lg:px-6">
        <button v-if="!desktop" type="button" class="icon-btn -ml-1" aria-label="打开导航" @click="drawer = true"><Menu class="h-4.5 w-4.5" /></button>
        <nav class="flex min-w-0 items-center gap-1.5 text-[13px]" aria-label="面包屑">
          <span class="hidden text-slate-500 sm:inline">管理后台</span>
          <template v-if="current?.group">
            <span class="hidden text-slate-500 sm:inline" aria-hidden="true">/</span>
            <span class="hidden text-slate-500 sm:inline">{{ current.group }}</span>
          </template>
          <span class="hidden text-slate-500 sm:inline" aria-hidden="true">/</span>
          <span class="truncate font-semibold text-white">{{ current?.label ?? '' }}</span>
        </nav>
        <div class="flex-1" />
        <button type="button" class="cmd-btn" aria-label="打开命令面板" @click="palette = true">
          <Search class="h-3.5 w-3.5" />
          <span class="hidden md:inline">搜索页面、任务、用户…</span>
          <span class="ac-kbd hidden md:inline-flex">{{ isMac ? '⌘' : 'Ctrl' }} K</span>
        </button>
        <button
          type="button"
          class="icon-btn"
          :aria-label="prefs.theme === 'dark' ? '切换浅色' : '切换深色'"
          :title="prefs.theme === 'dark' ? '浅色' : '深色'"
          @click="prefs.toggleTheme()"
        >
          <Sun v-if="prefs.theme === 'dark'" class="h-4 w-4" />
          <Moon v-else class="h-4 w-4" />
        </button>
        <div ref="userAnchor" class="inline-flex">
          <button type="button" class="user-btn" :aria-expanded="userOpen" aria-haspopup="menu" @click="userOpen = !userOpen">
            <span class="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--pastel-mint)] text-xs font-bold text-[var(--pastel-mint-ink)]">{{ initial }}</span>
            <span class="hidden max-w-32 truncate text-[13px] font-medium text-white sm:inline">{{ auth.displayName }}</span>
            <ChevronDown class="hidden h-3.5 w-3.5 text-slate-400 sm:block" />
          </button>
        </div>
        <Teleport to="body">
          <div v-if="userOpen" ref="userMenu" class="popover-menu w-52" :style="userStyle" role="menu">
            <div class="px-2.5 pt-1.5 pb-2">
              <div class="truncate text-[13px] font-semibold text-white">{{ auth.displayName }}</div>
              <div class="text-[11px] text-slate-400">@{{ auth.user?.username }} · 管理员</div>
            </div>
            <div class="my-1 h-px bg-[var(--cs-line)]" />
            <RouterLink :to="appTarget" class="menu-item" role="menuitem" @click="userOpen = false"><ArrowLeftToLine class="h-3.5 w-3.5" /> 返回应用</RouterLink>
            <button type="button" class="menu-item w-full" role="menuitem" @click="logout"><LogOut class="h-3.5 w-3.5" /> 退出登录</button>
          </div>
        </Teleport>
      </header>

      <main class="min-h-0 flex-1 overflow-y-auto" data-admin-scroll>
        <RouterView />
      </main>
    </div>

    <CommandPalette v-model="palette" />
  </div>
</template>

<style scoped>
.ac-root {
  background: var(--cs-bg);
}
.ac-side {
  background: var(--ac-side, #111214);
  color: #f4f4f0;
  transition: width 0.18s ease;
}
html.dark .ac-side {
  box-shadow: inset -1px 0 0 rgb(255 255 255 / 0.06);
}
.ac-top {
  background: color-mix(in srgb, var(--cs-bg) 92%, transparent);
  backdrop-filter: saturate(1.2) blur(8px);
  border-bottom: 1px solid var(--cs-line);
}
.side-link {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  height: 34px;
  padding: 0 0.7rem;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--ac-side-text, rgb(244 244 240 / 0.62));
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.side-link:hover {
  color: #f4f4f0;
  background: var(--ac-side-hover, rgb(255 255 255 / 0.06));
}
.side-link-on {
  color: #ffffff !important;
  background: var(--ac-side-active, rgb(255 255 255 / 0.1)) !important;
  box-shadow: inset 2px 0 0 var(--pastel-mint-dot);
  font-weight: 600;
}
.side-btn {
  display: inline-flex;
  height: 2rem;
  width: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: rgb(244 244 240 / 0.75);
}
.side-btn:hover {
  background: rgb(255 255 255 / 0.08);
}
.cmd-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  height: 32px;
  min-width: 32px;
  justify-content: center;
  padding: 0 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--cs-line-strong);
  background: var(--cs-surface-solid);
  font-size: 12px;
  color: var(--color-slate-400);
}
@media (min-width: 768px) {
  .cmd-btn {
    width: 280px;
    justify-content: flex-start;
  }
  .cmd-btn .ac-kbd {
    margin-left: auto;
  }
}
.cmd-btn:hover {
  border-color: var(--color-slate-400);
}
.user-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  height: 34px;
  padding: 0 0.4rem 0 0.2rem;
  border-radius: 999px;
}
.user-btn:hover {
  background: var(--cs-line);
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  border-radius: 8px;
  padding: 0.45rem 0.6rem;
  font-size: 13px;
  color: var(--color-slate-100);
}
.menu-item:hover {
  background: var(--cs-line);
}
</style>
