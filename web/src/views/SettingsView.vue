<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { ModeSelection } from '@/api/types'
import { MODE_OPTIONS } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { HOME_ARTS, usePrefsStore } from '@/stores/prefs'

const prefs = usePrefsStore()

const auth = useAuthStore()
const PREF_KEY = 'cs_default_mode'
const defaultMode = ref<ModeSelection>((localStorage.getItem(PREF_KEY) as ModeSelection) || 'auto')
watch(defaultMode, (v) => localStorage.setItem(PREF_KEY, v))
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto max-w-2xl space-y-4 px-4 py-6">
      <h1 class="text-xl font-semibold text-white">设置</h1>
      <section class="glass p-4">
        <h2 class="card-title mb-3">账号</h2>
        <dl class="grid grid-cols-[6rem_1fr] gap-y-2 text-sm">
          <dt class="text-slate-400">用户名</dt>
          <dd>{{ auth.user?.username }}</dd>
          <dt class="text-slate-400">昵称</dt>
          <dd>{{ auth.user?.display_name || '—' }}</dd>
          <dt class="text-slate-400">角色</dt>
          <dd>{{ auth.user?.is_admin ? '管理员' : '成员' }}</dd>
          <dt class="text-slate-400">项目</dt>
          <dd class="font-mono text-xs text-slate-300">{{ auth.user?.project_id }}</dd>
        </dl>
      </section>
      <section class="glass p-4">
        <h2 class="card-title mb-3">偏好</h2>
        <label class="label" for="dm">首页默认模式</label>
        <select id="dm" v-model="defaultMode" class="input max-w-xs">
          <option v-for="m in MODE_OPTIONS" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
        <p class="mt-2 text-xs text-slate-500">仅保存在本浏览器。智能模式会根据需求建议执行路线，你可以在发送前修改。</p>

        <div class="hairline mt-4 flex items-start justify-between gap-4 border-t pt-4">
          <div>
            <div class="text-sm text-white" id="auto-open-label">搜索时自动打开浏览器</div>
            <p class="mt-0.5 text-xs text-slate-500">任务开始使用云端浏览器时，在右侧自动打开实时画面；关闭面板不影响后台任务。需要人工协助（如人机验证）时总会打开。</p>
          </div>
          <button
            role="switch"
            :aria-checked="prefs.autoOpenBrowser"
            aria-labelledby="auto-open-label"
            class="relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition"
            :class="prefs.autoOpenBrowser ? 'bg-brand-500' : 'bg-slate-500/40'"
            @click="prefs.setAutoOpenBrowser(!prefs.autoOpenBrowser)"
          >
            <span class="inline-block h-5 w-5 rounded-full bg-[#fff] shadow transition" :class="prefs.autoOpenBrowser ? 'translate-x-5' : 'translate-x-0.5'" />
          </button>
        </div>

        <div class="hairline mt-4 border-t pt-4">
          <div class="mb-2 text-sm text-white">外观</div>
          <div class="flex flex-wrap gap-2">
            <button class="chip" :class="prefs.theme === 'light' ? '!border-brand-400 text-brand-300' : ''" @click="prefs.setTheme('light')">浅色</button>
            <button class="chip" :class="prefs.theme === 'dark' ? '!border-brand-400 text-brand-300' : ''" @click="prefs.setTheme('dark')">深色</button>
          </div>
          <div class="mt-3 mb-2 text-xs text-slate-400">首页插画</div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="a in HOME_ARTS"
              :key="a.value"
              class="chip"
              :class="prefs.homeArt === a.value ? '!border-brand-400 text-brand-300' : ''"
              @click="prefs.setHomeArt(a.value)"
            >
              {{ a.label }}
            </button>
          </div>
        </div>
      </section>
      <section class="glass p-4 text-sm text-slate-300">
        <h2 class="card-title mb-2">模型与执行资源</h2>
        <p>模型密钥、搜索与浏览器执行资源由管理员在后台统一配置，普通使用无需自行搭建。</p>
        <RouterLink v-if="auth.user?.is_admin" to="/admin/llm" class="btn-secondary btn-sm mt-3">前往模型与智能体配置</RouterLink>
      </section>
    </div>
  </div>
</template>
