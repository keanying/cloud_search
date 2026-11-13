<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { ModeSelection } from '@/api/types'
import { MODE_OPTIONS } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'

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
      </section>
      <section class="glass p-4 text-sm text-slate-300">
        <h2 class="card-title mb-2">模型与执行资源</h2>
        <p>模型密钥、搜索与浏览器执行资源由管理员在后台统一配置，普通使用无需自行搭建。</p>
        <RouterLink v-if="auth.user?.is_admin" to="/admin/llm" class="btn-secondary btn-sm mt-3">前往模型与智能体配置</RouterLink>
      </section>
    </div>
  </div>
</template>
