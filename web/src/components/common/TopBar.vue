<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Bot, FileText, LogOut, MessageSquare, Moon, Plus, Settings, Sun, UserRound } from 'lucide-vue-next'
import BrandLogo from './BrandLogo.vue'
import HistoryDrawer from './HistoryDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import { usePrefsStore } from '@/stores/prefs'
import { useUiStore } from '@/stores/ui'
import { useFloating } from '@/lib/useFloating'
import AppLauncher from '@/components/home/AppLauncher.vue'
import ThemePicker from '@/components/home/ThemePicker.vue'

/** minimal：首页使用的极简顶栏（最近对话/成果入口在页面中央的快捷入口里） */
defineProps<{ title?: string | null; minimal?: boolean }>()
const auth = useAuthStore()
const prefs = usePrefsStore()
const ui = useUiStore()
const router = useRouter()
const menuOpen = ref(false)
const menuRoot = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const { style: menuStyle } = useFloating(menuRoot, menuEl, menuOpen, () => 'bottom-end')

function logout() {
  menuOpen.value = false
  auth.logout()
  router.replace({ name: 'login' })
}
const initial = () => (auth.displayName || 'U').slice(0, 1).toUpperCase()
</script>

<template>
  <header class="relative z-30 flex h-14 shrink-0 items-center gap-2 px-4 md:px-6">
    <!-- 回到新对话首页不会停止其他会话的任务 -->
    <RouterLink to="/" class="flex items-center gap-2 rounded-lg" aria-label="云搜浏览器，回到新对话">
      <BrandLogo :size="28" />
      <span class="text-[15px] font-semibold tracking-wide text-white">云搜浏览器</span>
    </RouterLink>
    <div v-if="title" class="hidden min-w-0 items-center gap-2 text-sm md:flex">
      <span class="text-slate-500">/</span>
      <span class="truncate text-slate-300">{{ title }}</span>
    </div>
    <div class="flex-1" />
    <template v-if="!minimal">
      <RouterLink v-if="title" to="/" class="btn-ghost btn-sm hidden sm:inline-flex" aria-label="新对话">
        <Plus class="h-4 w-4" /> 新对话
      </RouterLink>
      <button class="btn-ghost btn-sm" aria-label="最近对话" @click="ui.openHistory()">
        <MessageSquare class="h-4 w-4" /><span class="hidden sm:inline">最近对话</span>
      </button>
      <RouterLink to="/artifacts" class="btn-ghost btn-sm" aria-label="我的成果">
        <FileText class="h-4 w-4" /><span class="hidden sm:inline">我的成果</span>
      </RouterLink>
    </template>
    <ThemePicker v-if="minimal" />
    <button
      class="icon-btn"
      :aria-label="prefs.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
      :title="prefs.theme === 'dark' ? '浅色主题' : '深色主题'"
      @click="prefs.toggleTheme()"
    >
      <Sun v-if="prefs.theme === 'dark'" class="h-[18px] w-[18px]" />
      <Moon v-else class="h-[18px] w-[18px]" />
    </button>
    <RouterLink to="/settings" class="icon-btn" aria-label="设置" title="设置"><Settings class="h-[18px] w-[18px]" /></RouterLink>
    <AppLauncher />
    <div ref="menuRoot">
      <button
        class="ml-1 flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-violet-400 to-brand-600 text-sm font-semibold text-snow shadow-sm"
        :aria-expanded="menuOpen"
        aria-haspopup="menu"
        aria-label="用户菜单"
        @click="menuOpen = !menuOpen"
      >
        {{ initial() }}
      </button>
    </div>
    <Teleport to="body">
      <div v-if="menuOpen" ref="menuEl" role="menu" class="popover-menu w-52" :style="menuStyle" @click="menuOpen = false">
        <div class="hairline flex items-center gap-2 border-b px-3 py-2 text-sm">
          <UserRound class="h-4 w-4 text-slate-400" />
          <div class="min-w-0">
            <div class="truncate text-white">{{ auth.displayName }}</div>
            <div class="text-xs text-slate-500">{{ auth.user?.is_admin ? '管理员' : '成员' }}</div>
          </div>
        </div>
        <RouterLink to="/settings" role="menuitem" class="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-white/5">
          <Settings class="h-4 w-4" /> 设置
        </RouterLink>
        <RouterLink
          v-if="auth.user?.is_admin"
          to="/admin/llm"
          role="menuitem"
          class="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-white/5"
        >
          <Bot class="h-4 w-4" /> 管理后台
        </RouterLink>
        <button role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-white/5" @click="logout">
          <LogOut class="h-4 w-4" /> 退出登录
        </button>
      </div>
    </Teleport>
    <HistoryDrawer :open="ui.historyOpen" @close="ui.closeHistory()" />
  </header>
</template>
