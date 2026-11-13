<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { ModeSelection } from '@/api/types'
import { MODE_OPTIONS } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { HOME_ARTS, usePrefsStore } from '@/stores/prefs'
import PageHeader from '@/components/common/PageHeader.vue'

const prefs = usePrefsStore()

const auth = useAuthStore()
const PREF_KEY = 'cs_default_mode'
const defaultMode = ref<ModeSelection>((localStorage.getItem(PREF_KEY) as ModeSelection) || 'auto')
watch(defaultMode, (v) => localStorage.setItem(PREF_KEY, v))
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto max-w-3xl px-4 pt-6 pb-12 md:px-6">
      <PageHeader title="设置" desc="账号信息与本浏览器的使用偏好。" :parent="{ name: 'home' }" />

      <div class="grid gap-4 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <section class="card-lilac p-6">
          <div class="flex items-center gap-3">
            <span class="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--cs-surface-solid)] text-xl font-bold accent-ink">
              {{ (auth.displayName || 'U').slice(0, 1).toUpperCase() }}
            </span>
            <div class="min-w-0">
              <div class="truncate text-lg font-bold tracking-tight text-white">{{ auth.user?.display_name || auth.user?.username }}</div>
              <span class="pill bg-[var(--cs-surface-solid)] text-slate-200">{{ auth.user?.is_admin ? '🛡️ 管理员' : '🙂 成员' }}</span>
            </div>
          </div>
          <dl class="tile mt-5 grid grid-cols-[4.5rem_1fr] gap-y-2 p-4 text-sm">
            <dt class="text-slate-400">用户名</dt>
            <dd class="truncate text-slate-100">{{ auth.user?.username }}</dd>
            <dt class="text-slate-400">昵称</dt>
            <dd class="truncate text-slate-100">{{ auth.user?.display_name || '—' }}</dd>
            <dt class="text-slate-400">项目</dt>
            <dd class="truncate font-mono text-xs leading-5 text-slate-300">{{ auth.user?.project_id }}</dd>
          </dl>
        </section>

        <section class="surface p-6">
          <h2 class="card-title">偏好</h2>
          <label class="label mt-4" for="dm">首页默认模式</label>
          <select id="dm" v-model="defaultMode" class="input max-w-xs">
            <option v-for="m in MODE_OPTIONS" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
          <p class="mt-2 text-xs text-slate-500">仅保存在本浏览器。智能模式会根据需求建议执行路线，你可以在发送前修改。</p>

          <div class="hairline mt-5 flex items-start justify-between gap-4 border-t pt-5">
            <div>
              <div class="text-sm font-semibold text-white" id="auto-open-label">搜索时自动打开浏览器</div>
              <p class="mt-0.5 text-xs text-slate-500">任务开始使用云端浏览器时，在右侧自动打开实时画面；关闭面板不影响后台任务。需要人工协助（如人机验证）时总会打开。</p>
            </div>
            <button
              role="switch"
              :aria-checked="prefs.autoOpenBrowser"
              aria-labelledby="auto-open-label"
              class="relative mt-0.5 inline-flex h-7 w-12 shrink-0 items-center rounded-full transition"
              :class="prefs.autoOpenBrowser ? 'bg-[var(--cs-ink)]' : 'bg-slate-500/40'"
              @click="prefs.setAutoOpenBrowser(!prefs.autoOpenBrowser)"
            >
              <span
                class="inline-block h-5 w-5 rounded-full shadow transition"
                :class="prefs.autoOpenBrowser ? 'translate-x-6 bg-[var(--cs-on-ink)]' : 'translate-x-1 bg-[#fff]'"
              />
            </button>
          </div>

          <div class="hairline mt-5 border-t pt-5">
            <div class="mb-2 text-sm font-semibold text-white">外观</div>
            <div class="flex flex-wrap gap-2">
              <button class="chip" :class="prefs.theme === 'light' ? 'chip-active' : ''" @click="prefs.setTheme('light')">☀️ 浅色</button>
              <button class="chip" :class="prefs.theme === 'dark' ? 'chip-active' : ''" @click="prefs.setTheme('dark')">🌙 深色</button>
            </div>
            <div class="mt-4 mb-2 text-xs font-semibold text-slate-400">首页插画</div>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="a in HOME_ARTS"
                :key="a.value"
                class="chip"
                :class="prefs.homeArt === a.value ? 'chip-active' : ''"
                @click="prefs.setHomeArt(a.value)"
              >
                {{ a.label }}
              </button>
            </div>
          </div>
        </section>

        <section class="card-butter p-6 md:col-span-2">
          <div class="flex flex-wrap items-center gap-4">
            <span class="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--cs-surface-solid)] text-xl" aria-hidden="true">🔑</span>
            <div class="min-w-0 flex-1">
              <h2 class="card-title">模型与执行资源</h2>
              <p class="mt-0.5 text-sm text-slate-200">模型密钥、搜索与浏览器执行资源由管理员在后台统一配置，普通使用无需自行搭建。</p>
            </div>
            <RouterLink v-if="auth.user?.is_admin" to="/admin/llm" class="btn-primary btn-sm">前往管理后台</RouterLink>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
