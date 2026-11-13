<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Bot, FileText, LogOut, MessageSquare, Plus, Settings, UserRound } from 'lucide-vue-next'
import BrandLogo from './BrandLogo.vue'
import HistoryDrawer from './HistoryDrawer.vue'
import { useAuthStore } from '@/stores/auth'

defineProps<{ title?: string | null }>()
const auth = useAuthStore()
const router = useRouter()
const historyOpen = ref(false)
const menuOpen = ref(false)
const menuRoot = ref<HTMLElement | null>(null)

function onDoc(e: MouseEvent) {
  if (menuRoot.value && !menuRoot.value.contains(e.target as Node)) menuOpen.value = false
}
onMounted(() => document.addEventListener('mousedown', onDoc))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDoc))

function logout() {
  auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <header class="relative z-30 flex h-14 shrink-0 items-center gap-3 px-4 md:px-6">
    <!-- 回到新对话首页不会停止其他会话的任务 -->
    <RouterLink to="/" class="flex items-center gap-2.5 rounded-lg" aria-label="云搜浏览器，回到新对话">
      <BrandLogo :size="30" />
      <span class="text-lg font-semibold tracking-wide text-white">云搜浏览器</span>
    </RouterLink>
    <div v-if="title" class="hidden min-w-0 items-center gap-2 text-sm text-slate-400 md:flex">
      <span class="text-slate-600">/</span>
      <span class="truncate text-slate-200">{{ title }}</span>
    </div>
    <div class="flex-1" />
    <RouterLink v-if="title" to="/" class="btn-ghost hidden sm:inline-flex" aria-label="新对话">
      <Plus class="h-4 w-4" /> 新对话
    </RouterLink>
    <button class="btn-ghost" aria-label="最近对话" @click="historyOpen = true">
      <MessageSquare class="h-4 w-4" /><span class="hidden sm:inline">最近对话</span>
    </button>
    <RouterLink to="/artifacts" class="btn-ghost" aria-label="我的成果">
      <FileText class="h-4 w-4" /><span class="hidden sm:inline">我的成果</span>
    </RouterLink>
    <div ref="menuRoot" class="relative">
      <button
        class="flex h-9 w-9 items-center justify-center rounded-full border border-white/15 bg-white/10 hover:bg-white/20"
        :aria-expanded="menuOpen"
        aria-haspopup="menu"
        aria-label="用户菜单"
        @click="menuOpen = !menuOpen"
      >
        <UserRound class="h-5 w-5" />
      </button>
      <div v-if="menuOpen" role="menu" class="glass-strong absolute top-full right-0 mt-2 w-52 p-1" @click="menuOpen = false">
        <div class="border-b border-white/10 px-3 py-2 text-sm">
          <div class="truncate text-white">{{ auth.displayName }}</div>
          <div class="text-xs text-slate-500">{{ auth.user?.is_admin ? '管理员' : '成员' }}</div>
        </div>
        <RouterLink to="/settings" role="menuitem" class="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-white/10">
          <Settings class="h-4 w-4" /> 设置
        </RouterLink>
        <RouterLink
          v-if="auth.user?.is_admin"
          to="/admin/llm"
          role="menuitem"
          class="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-white/10"
        >
          <Bot class="h-4 w-4" /> 模型与智能体
        </RouterLink>
        <button role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-white/10" @click="logout">
          <LogOut class="h-4 w-4" /> 退出登录
        </button>
      </div>
    </div>
    <HistoryDrawer :open="historyOpen" @close="historyOpen = false" />
  </header>
</template>
