<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { ArrowLeftToLine, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun, X } from 'lucide-vue-next'
import BrandLogo from '@/components/common/BrandLogo.vue'
import { ADMIN_NAV } from '@/lib/adminNav'
import { MEDIUM_QUERY, useMedia } from '@/lib/useMedia'
import { useAuthStore } from '@/stores/auth'
import { usePrefsStore } from '@/stores/prefs'
import { useUiStore } from '@/stores/ui'

/** 管理后台布局：左侧深色导航（可收起为图标栏；<1024px 为抽屉）+ 右侧全宽内容区 */
const auth = useAuthStore()
const prefs = usePrefsStore()
const ui = useUiStore()
const route = useRoute()
const desktop = useMedia(MEDIUM_QUERY)

const KEY = 'cs_admin_collapsed'
const collapsed = ref(localStorage.getItem(KEY) === '1')
watch(collapsed, (v) => localStorage.setItem(KEY, v ? '1' : '0'))
const drawer = ref(false)
watch(() => route.fullPath, () => (drawer.value = false))

const mini = computed(() => desktop.value && collapsed.value)
const initial = computed(() => (auth.displayName || 'U').slice(0, 1).toUpperCase())
const appTarget = computed(() => (ui.lastChatId ? { name: 'chat', params: { id: ui.lastChatId } } : { name: 'home' }))
const current = computed(() => ADMIN_NAV.flatMap((g) => g.items).find((i) => i.name === route.name))
</script>

<template>
  <div class="admin-root flex h-full">
    <!-- 小屏顶栏 -->
    <header v-if="!desktop" class="admin-topbar fixed inset-x-3 top-3 z-[60] flex items-center gap-2 rounded-full py-1.5 pr-3 pl-1.5">
      <button type="button" class="side-btn" aria-label="打开导航" @click="drawer = true"><Menu class="h-5 w-5" /></button>
      <BrandLogo :size="30" />
      <span class="truncate text-sm font-bold">{{ current?.label ?? '管理后台' }}</span>
    </header>

    <div v-if="!desktop && drawer" class="fixed inset-0 z-[70] bg-black/40" @click="drawer = false" />

    <aside
      class="admin-side z-[80] flex shrink-0 flex-col"
      :class="[
        desktop ? 'relative m-3 mr-0 h-[calc(100%-1.5rem)]' : 'fixed inset-y-3 left-3 transition-transform duration-200',
        !desktop && !drawer ? '-translate-x-[110%]' : '',
        mini ? 'w-[76px]' : 'w-[248px]',
      ]"
      aria-label="管理后台导航"
    >
      <div class="flex items-center gap-2.5 px-4 pt-5 pb-4" :class="mini ? 'justify-center !px-0' : ''">
        <BrandLogo :size="34" />
        <div v-if="!mini" class="min-w-0 flex-1 leading-tight">
          <div class="text-[15px] font-bold tracking-tight">云搜浏览器</div>
          <div class="text-[11px] font-medium opacity-55">管理后台</div>
        </div>
        <button v-if="!desktop" type="button" class="side-btn" aria-label="关闭导航" @click="drawer = false"><X class="h-4 w-4" /></button>
      </div>

      <nav class="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        <div v-for="(g, gi) in ADMIN_NAV" :key="gi" class="mt-3 first:mt-1">
          <div v-if="g.group && !mini" class="mb-1.5 px-3 text-[11px] font-semibold tracking-[0.12em] opacity-40">{{ g.group }}</div>
          <div v-else-if="g.group" class="mx-auto my-2 h-px w-8 bg-white/10" />
          <RouterLink
            v-for="it in g.items"
            :key="it.name"
            :to="{ name: it.name }"
            class="side-link"
            :class="[route.name === it.name ? 'side-link-on' : '', mini ? 'justify-center !px-0' : '']"
            :title="mini ? it.label : undefined"
            :aria-current="route.name === it.name ? 'page' : undefined"
          >
            <component :is="it.icon" class="h-[18px] w-[18px] shrink-0" />
            <span v-if="!mini" class="truncate">{{ it.label }}</span>
            <span v-if="route.name === it.name && !mini" class="ml-auto h-1.5 w-1.5 rounded-full bg-[var(--pastel-mint-dot)]" />
          </RouterLink>
        </div>
      </nav>

      <div class="px-3 pb-3">
        <div class="side-user" :class="mini ? 'flex-col !px-0 !py-3' : ''">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[var(--pastel-mint)] text-sm font-bold text-[var(--pastel-mint-ink)]">
            {{ initial }}
          </span>
          <div v-if="!mini" class="min-w-0 flex-1 leading-tight">
            <div class="truncate text-sm font-semibold">{{ auth.displayName }}</div>
            <div class="text-[11px] opacity-55">管理员</div>
          </div>
          <button
            type="button"
            class="side-btn"
            :aria-label="prefs.theme === 'dark' ? '切换浅色' : '切换深色'"
            :title="prefs.theme === 'dark' ? '浅色' : '深色'"
            @click="prefs.toggleTheme()"
          >
            <Sun v-if="prefs.theme === 'dark'" class="h-4 w-4" />
            <Moon v-else class="h-4 w-4" />
          </button>
        </div>
        <RouterLink :to="appTarget" class="side-link mt-2" :class="mini ? 'justify-center !px-0' : ''" :title="mini ? '返回应用' : undefined">
          <ArrowLeftToLine class="h-[18px] w-[18px] shrink-0" />
          <span v-if="!mini">返回应用</span>
        </RouterLink>
        <button
          v-if="desktop"
          type="button"
          class="side-link w-full"
          :class="mini ? 'justify-center !px-0' : ''"
          :title="mini ? '展开导航' : undefined"
          @click="collapsed = !collapsed"
        >
          <PanelLeftOpen v-if="mini" class="h-[18px] w-[18px]" />
          <template v-else><PanelLeftClose class="h-[18px] w-[18px]" /><span>收起导航</span></template>
        </button>
      </div>
    </aside>

    <main class="min-w-0 flex-1 overflow-y-auto" :class="desktop ? '' : 'pt-16'">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.admin-root {
  background: var(--cs-bg);
}
.admin-side {
  background: var(--cs-bar);
  color: var(--cs-on-bar);
  border-radius: 28px;
  box-shadow: var(--cs-shadow-lg);
  transition: width 0.2s ease;
}
html.dark .admin-side {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}
.admin-topbar {
  background: var(--cs-bar);
  color: var(--cs-on-bar);
  box-shadow: var(--cs-shadow-lg);
}
.side-link {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  height: 2.6rem;
  padding: 0 0.85rem;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 500;
  color: rgb(244 244 240 / 0.66);
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}
.side-link:hover {
  color: #f4f4f0;
  background: rgb(255 255 255 / 0.06);
}
.side-link-on {
  color: #111214 !important;
  background: #f4f4f0 !important;
  font-weight: 600;
}
.side-btn {
  display: inline-flex;
  height: 2.25rem;
  width: 2.25rem;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: rgb(244 244 240 / 0.75);
}
.side-btn:hover {
  background: rgb(255 255 255 / 0.08);
  color: #f4f4f0;
}
.side-user {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0.5rem 0.6rem 0.6rem;
  border-radius: 22px;
  background: rgb(255 255 255 / 0.06);
}
</style>
