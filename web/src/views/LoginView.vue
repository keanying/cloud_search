<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Loader2 } from 'lucide-vue-next'
import BrandLogo from '@/components/common/BrandLogo.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const tab = ref<'login' | 'register'>(route.query.tab === 'register' ? 'register' : 'login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

async function submit() {
  error.value = null
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  busy.value = true
  try {
    if (tab.value === 'login') await auth.login(username.value.trim(), password.value)
    else await auth.register(username.value.trim(), password.value, displayName.value.trim() || undefined)
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/'
    router.replace(redirect)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex min-h-full items-center justify-center gap-16 px-4 py-10">
    <!-- 宽屏：左侧几张粉彩小卡片，说明它会做什么 -->
    <div class="hidden max-w-md flex-1 lg:block" aria-hidden="true">
      <h2 class="text-[40px] leading-[1.15] font-bold tracking-tight text-white">一个问题，<br />一份能直接用的成果。</h2>
      <p class="mt-3 text-[15px] text-slate-400">它会自己去搜、去读、去核对，遇到验证码再叫你帮一下。</p>
      <div class="relative mt-10 h-[260px]">
        <div class="card-mint absolute top-0 left-0 w-64 p-4">
          <div class="text-xs font-bold accent-ink">⏳ 执行中</div>
          <div class="mt-2 flex gap-2">
            <div class="tile flex-1 px-3 py-2"><div class="text-2xl font-bold text-white">9</div><div class="text-xs text-slate-300">搜索</div></div>
            <div class="tile flex-1 px-3 py-2"><div class="text-2xl font-bold text-white">12</div><div class="text-xs text-slate-300">已读来源</div></div>
          </div>
        </div>
        <div class="card-butter absolute top-24 left-48 w-60 rotate-[-3deg] p-4">
          <div class="text-xs font-bold accent-ink">✋ 需要你</div>
          <div class="mt-1 text-sm font-semibold text-white">网站要求人机验证，点一下就好</div>
        </div>
        <div class="card-lilac absolute top-44 left-6 w-56 rotate-[2deg] p-4">
          <div class="text-xs font-bold accent-ink">✅ 已完成</div>
          <div class="mt-1 flex gap-1.5">
            <span class="pill bg-[var(--cs-surface-solid)] text-slate-200">Word</span>
            <span class="pill bg-[var(--cs-surface-solid)] text-slate-200">PDF</span>
            <span class="pill bg-[var(--cs-surface-solid)] text-slate-200">Excel</span>
          </div>
        </div>
      </div>
    </div>
    <div class="w-full max-w-sm">
      <div class="mb-8 flex flex-col items-center gap-3">
        <BrandLogo :size="56" />
        <h1 class="text-[28px] font-bold tracking-tight text-white">云搜浏览器</h1>
        <p class="text-sm text-slate-400">从一个问题开始，让 AI 帮你搜索、整理数据、生成报告</p>
      </div>
      <form class="glass-strong !rounded-[32px] p-7" @submit.prevent="submit">
        <div class="sunken hairline mb-6 grid grid-cols-2 rounded-full border p-1" role="tablist">
          <button
            type="button"
            role="tab"
            :aria-selected="tab === 'login'"
            class="rounded-full py-2 text-sm font-semibold"
            :class="tab === 'login' ? 'chip-active' : 'text-slate-400'"
            @click="tab = 'login'"
          >
            登录
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="tab === 'register'"
            class="rounded-full py-2 text-sm font-semibold"
            :class="tab === 'register' ? 'chip-active' : 'text-slate-400'"
            @click="tab = 'register'"
          >
            注册
          </button>
        </div>
        <div class="space-y-4">
          <div>
            <label class="label" for="u">用户名</label>
            <input id="u" v-model="username" class="input" autocomplete="username" required minlength="3" />
          </div>
          <div v-if="tab === 'register'">
            <label class="label" for="d">昵称（可选）</label>
            <input id="d" v-model="displayName" class="input" autocomplete="nickname" />
          </div>
          <div>
            <label class="label" for="p">密码</label>
            <input
              id="p"
              v-model="password"
              type="password"
              class="input"
              :autocomplete="tab === 'login' ? 'current-password' : 'new-password'"
              required
              :minlength="tab === 'register' ? 6 : undefined"
            />
          </div>
          <p v-if="error" class="text-sm text-rose-300" role="alert">{{ error }}</p>
          <button type="submit" class="btn-primary w-full !py-3" :disabled="busy">
            <Loader2 v-if="busy" class="h-4 w-4 animate-spin" />
            {{ tab === 'login' ? '登录' : '注册并登录' }}
          </button>
          <p v-if="tab === 'register'" class="text-xs text-slate-500">首个注册的账号将成为管理员，可配置模型与智能体。</p>
        </div>
      </form>
    </div>
  </div>
</template>
