<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  Bot,
  ChevronDown,
  FileText,
  History,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  Settings,
  Sun,
  UserRound,
} from 'lucide-vue-next'
import BrandLogo from './BrandLogo.vue'
import HistoryDrawer from './HistoryDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import { usePrefsStore } from '@/stores/prefs'
import { useUiStore } from '@/stores/ui'
import { useFloating } from '@/lib/useFloating'
import { WIDE_QUERY, useMedia } from '@/lib/useMedia'
import AppLauncher from '@/components/home/AppLauncher.vue'
import ThemePicker from '@/components/home/ThemePicker.vue'

/** landing：首页落地页模式——浮在插画首屏上，滚动后变为不透明并显示介绍区块导航；
 *  否则为应用顶栏：近黑色圆角浮条，居中导航 */
defineProps<{ landing?: boolean }>()
// 多根节点（顶栏 + 弹出菜单 + 抽屉）：class 等属性只绑定到顶栏
defineOptions({ inheritAttrs: false })
const auth = useAuthStore()
const prefs = usePrefsStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const wide = useMedia(WIDE_QUERY)
const menuOpen = ref(false)
const menuRoot = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const { style: menuStyle } = useFloating(menuRoot, menuEl, menuOpen, () => 'bottom-end')

function logout() {
  menuOpen.value = false
  auth.logout()
  router.replace({ name: 'login' })
}
const initial = computed(() => (auth.displayName || 'U').slice(0, 1).toUpperCase())
const isChat = computed(() => route.name === 'chat')

/** “对话”：回到最近打开的对话；没有则去首页新建 */
const chatTarget = computed(() =>
  ui.lastChatId ? { name: 'chat', params: { id: ui.lastChatId } } : { name: 'home' },
)
const APP_NAV = computed(() => [
  { key: 'chat', label: '对话', icon: MessageSquare, to: chatTarget.value, active: isChat.value },
  { key: 'artifacts', label: '我的成果', icon: FileText, to: { name: 'artifacts' }, active: route.name === 'artifacts' },
  { key: 'settings', label: '设置', icon: Settings, to: { name: 'settings' }, active: route.name === 'settings' },
  ...(auth.user?.is_admin
    ? [{ key: 'admin', label: '管理后台', icon: Bot, to: { name: 'admin-overview' }, active: route.path.startsWith('/admin') }]
    : []),
])

const NAV = [
  { id: 'features', label: '功能亮点' },
  { id: 'how', label: '工作方式' },
  { id: 'scenarios', label: '使用场景' },
  { id: 'security', label: '安全可信' },
  { id: 'faq', label: '常见问题' },
]
function goSection(id: string) {
  document.getElementById(id)?.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'start',
  })
}
</script>

<template>
  <!-- ============================================================ 首页落地页顶栏 -->
  <header
    v-if="landing"
    v-bind="$attrs"
    class="z-40 flex h-16 shrink-0 items-center gap-2 px-4 transition-[background-color,box-shadow] duration-300 md:px-8"
    :class="ui.landingScrolled ? 'landing-header-solid' : ''"
  >
    <RouterLink to="/" class="flex items-center gap-2 rounded-full" aria-label="云搜浏览器，回到首页">
      <BrandLogo :size="30" />
      <span class="text-base font-bold tracking-tight text-white">云搜浏览器</span>
    </RouterLink>
    <div class="flex-1" />
    <nav
      v-if="ui.landingScrolled"
      class="absolute left-1/2 hidden -translate-x-1/2 items-center gap-1 lg:flex"
      aria-label="产品介绍导航"
    >
      <button
        v-for="n in NAV"
        :key="n.id"
        type="button"
        class="rounded-full px-3.5 py-1.5 text-sm font-medium transition"
        :class="ui.activeSection === n.id ? 'chip-active' : 'text-slate-300 hover:text-white'"
        :aria-current="ui.activeSection === n.id ? 'true' : undefined"
        @click="goSection(n.id)"
      >
        {{ n.label }}
      </button>
    </nav>
    <ThemePicker v-if="!ui.landingScrolled" />
    <button
      class="icon-btn"
      :aria-label="prefs.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
      :title="prefs.theme === 'dark' ? '浅色主题' : '深色主题'"
      @click="prefs.toggleTheme()"
    >
      <Sun v-if="prefs.theme === 'dark'" class="h-[18px] w-[18px]" />
      <Moon v-else class="h-[18px] w-[18px]" />
    </button>
    <template v-if="!auth.user">
      <RouterLink :to="{ name: 'login', query: { redirect: '/' } }" class="btn-ghost btn-sm">登录</RouterLink>
      <RouterLink :to="{ name: 'login', query: { redirect: '/', tab: 'register' } }" class="btn-primary btn-sm">免费开始</RouterLink>
    </template>
    <template v-else>
      <RouterLink to="/settings" class="icon-btn" aria-label="设置" title="设置"><Settings class="h-[18px] w-[18px]" /></RouterLink>
      <AppLauncher />
      <div ref="menuRoot">
        <button
          class="avatar-holo ml-1 flex h-9 w-9 items-center justify-center rounded-full text-sm font-bold"
          :aria-expanded="menuOpen"
          aria-haspopup="menu"
          aria-label="用户菜单"
          @click="menuOpen = !menuOpen"
        >
          {{ initial }}
        </button>
      </div>
    </template>
  </header>

  <!-- ============================================================ 应用顶栏（磨砂玻璃浮条） -->
  <header
    v-else
    v-bind="$attrs"
    class="app-bar relative z-40 mx-3 mt-3 flex h-14 shrink-0 items-center gap-2 rounded-[22px] px-2.5 sm:px-3"
  >
    <button
      v-if="isChat && !wide"
      class="bar-btn"
      aria-label="打开对话列表"
      title="对话列表"
      @click="ui.sidebarDrawer = true"
    >
      <Menu class="h-[18px] w-[18px]" />
    </button>
    <RouterLink to="/" class="flex shrink-0 items-center gap-2 rounded-full pr-1 sm:pr-2" aria-label="云搜浏览器，回到首页">
      <BrandLogo :size="32" />
      <span class="hidden text-[15px] font-bold tracking-tight sm:inline">云搜浏览器</span>
    </RouterLink>

    <nav class="flex min-w-0 flex-1 items-center justify-center gap-0.5 sm:gap-1" aria-label="主导航">
      <RouterLink
        v-for="n in APP_NAV"
        :key="n.key"
        :to="n.to"
        class="bar-nav"
        :class="n.active ? 'bar-nav-active' : ''"
        :aria-current="n.active ? 'page' : undefined"
        :title="n.label"
      >
        <component :is="n.icon" class="h-4 w-4 shrink-0" />
        <span class="hidden md:inline">{{ n.label }}</span>
      </RouterLink>
    </nav>

    <button
      v-if="auth.user && !isChat"
      class="bar-btn"
      aria-label="最近对话"
      title="最近对话"
      @click="ui.openHistory()"
    >
      <History class="h-[18px] w-[18px]" />
    </button>
    <button
      class="bar-btn"
      :aria-label="prefs.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
      :title="prefs.theme === 'dark' ? '浅色主题' : '深色主题'"
      @click="prefs.toggleTheme()"
    >
      <Sun v-if="prefs.theme === 'dark'" class="h-[18px] w-[18px]" />
      <Moon v-else class="h-[18px] w-[18px]" />
    </button>
    <div v-if="auth.user" ref="menuRoot">
      <button
        class="flex shrink-0 items-center gap-2 rounded-full bg-white/[0.08] p-1 text-sm transition-colors hover:bg-white/[0.14] sm:pr-2.5"
        :aria-expanded="menuOpen"
        aria-haspopup="menu"
        aria-label="用户菜单"
        @click="menuOpen = !menuOpen"
      >
        <span class="avatar-holo flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold">{{ initial }}</span>
        <span class="hidden max-w-[8rem] truncate font-semibold lg:inline">{{ auth.displayName }}</span>
        <ChevronDown class="hidden h-4 w-4 opacity-60 sm:block" />
      </button>
    </div>
    <RouterLink v-else :to="{ name: 'login' }" class="btn-primary">登录</RouterLink>
  </header>

  <Teleport to="body">
    <div v-if="menuOpen" ref="menuEl" role="menu" class="popover-menu w-56" :style="menuStyle" @click="menuOpen = false">
      <div class="hairline mb-1 flex items-center gap-2.5 border-b px-3 py-2.5 text-sm">
        <span class="avatar-holo flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold">
          <UserRound class="h-4 w-4" />
        </span>
        <div class="min-w-0">
          <div class="truncate font-semibold text-white">{{ auth.displayName }}</div>
          <div class="text-xs text-slate-500">{{ auth.user?.is_admin ? '管理员' : '成员' }}</div>
        </div>
      </div>
      <RouterLink to="/settings" role="menuitem" class="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-200 hover:bg-white/5">
        <Settings class="h-4 w-4" /> 设置
      </RouterLink>
      <RouterLink
        v-if="auth.user?.is_admin"
        to="/admin/overview"
        role="menuitem"
        class="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-200 hover:bg-white/5"
      >
        <Bot class="h-4 w-4" /> 管理后台
      </RouterLink>
      <button role="menuitem" class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-200 hover:bg-white/5" @click="logout">
        <LogOut class="h-4 w-4" /> 退出
      </button>
    </div>
  </Teleport>
  <HistoryDrawer v-if="auth.user" :open="ui.historyOpen" @close="ui.closeHistory()" />
</template>

<style scoped>
.app-bar {
  background-color: var(--cs-bar);
  color: var(--cs-on-bar);
  border: 1px solid var(--cs-rim);
  box-shadow: var(--cs-shadow);
  backdrop-filter: var(--cs-blur);
  -webkit-backdrop-filter: var(--cs-blur);
}
.bar-btn {
  display: inline-flex;
  height: 2.25rem;
  width: 2.25rem;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  color: color-mix(in srgb, var(--cs-on-bar) 80%, transparent);
  background-color: var(--cs-surface-solid);
  box-shadow: inset 0 0 0 1px var(--cs-line);
  transition: background-color 0.15s, color 0.15s;
}
.bar-btn:hover {
  background-color: color-mix(in srgb, var(--cs-ink) 10%, var(--cs-surface-solid));
  color: var(--cs-on-bar);
}
.bar-nav {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.4rem;
  border-radius: 9999px;
  padding: 0.5rem 0.65rem;
  font-size: 0.875rem;
  font-weight: 600;
  white-space: nowrap;
  color: color-mix(in srgb, var(--cs-on-bar) 68%, transparent);
  transition: background-color 0.15s, color 0.15s;
}
@media (min-width: 768px) {
  .bar-nav {
    padding: 0.5rem 0.9rem;
  }
}
.bar-nav:hover {
  color: var(--cs-on-bar);
  background-color: color-mix(in srgb, var(--cs-on-bar) 6%, transparent);
}
.bar-nav-active,
.bar-nav-active:hover {
  background-color: var(--cs-ink);
  background-image: var(--cs-ink-grad);
  color: var(--cs-on-ink);
  box-shadow: var(--cs-ink-glow);
}
</style>
