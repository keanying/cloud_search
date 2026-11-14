<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import type { AdminTask, AdminUser, AdminUserDetail } from '@/api/types'
import { api } from '@/api/client'
import StatusPill from '@/components/admin/StatusPill.vue'
import SideDrawer from '@/components/common/SideDrawer.vue'
import { compact, hueTone, taskPastel } from '@/lib/adminFormat'
import { formatTime, modeLabel, relativeTime, taskStatusLabel } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

/** 用户详情抽屉：用量、最近任务；设为/取消管理员、停用/启用（均需确认） */
const props = defineProps<{ userId: string | null }>()
const emit = defineEmits<{ close: []; updated: [u: AdminUser]; openTask: [t: AdminTask] }>()
const auth = useAuthStore()
const toast = useToastStore()
const data = ref<AdminUserDetail | null>(null)
const busy = ref(false)

watch(
  () => props.userId,
  async (id) => {
    data.value = null
    if (!id) return
    try {
      const d = await api.adminUser(id)
      if (props.userId === id) data.value = d
    } catch (e) {
      toast.error(e, '加载用户详情失败')
    }
  },
  { immediate: true },
)
const open = computed({ get: () => !!props.userId, set: (v: boolean) => !v && emit('close') })
const u = computed(() => data.value?.user)
const isMe = computed(() => u.value?.user_id === auth.user?.user_id)

async function patch(body: { is_admin?: boolean; user_status?: 'active' | 'disabled' }, msg: string, confirmText: string) {
  if (!u.value || !confirm(confirmText)) return
  busy.value = true
  try {
    const nu = await api.patchAdminUser(u.value.user_id, body)
    if (data.value) data.value = { ...data.value, user: nu }
    emit('updated', nu)
    toast.push(msg, 'success')
  } catch (e) {
    toast.error(e)
  } finally {
    busy.value = false
  }
}
function toggleAdmin() {
  if (!u.value) return
  const name = u.value.display_name || u.value.username
  const v = !u.value.is_admin
  void patch(
    { is_admin: v },
    v ? '已设为管理员' : '已取消管理员',
    v ? `将「${name}」设为管理员？管理员可以修改模型密钥和全局配置。` : `取消「${name}」的管理员权限？`,
  )
}
function toggleStatus() {
  if (!u.value) return
  const name = u.value.display_name || u.value.username
  const next = u.value.user_status === 'active' ? 'disabled' : 'active'
  void patch(
    { user_status: next },
    next === 'disabled' ? '已停用' : '已启用',
    next === 'disabled' ? `停用「${name}」？停用后立即退出登录、无法再登录，已有任务不受影响。` : `重新启用「${name}」？`,
  )
}
</script>

<template>
  <SideDrawer v-model="open" title="用户详情" :width="560">
    <template #title>
      <div v-if="u" class="flex items-center gap-3">
        <span
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold"
          :style="{ background: `var(--pastel-${hueTone(u.username)})`, color: `var(--pastel-${hueTone(u.username)}-ink)` }"
        >{{ (u.display_name || u.username).slice(0, 1).toUpperCase() }}</span>
        <div class="min-w-0">
          <h2 class="flex items-center gap-2 text-base font-bold tracking-tight text-white">
            {{ u.display_name || u.username }}
            <span v-if="isMe" class="text-[11px] font-medium text-slate-400">（你）</span>
          </h2>
          <div class="flex flex-wrap items-center gap-2 text-[12px] text-slate-400">
            <span class="font-mono">@{{ u.username }}</span>
            <StatusPill v-if="u.is_admin" tone="lilac" text="管理员" />
            <StatusPill :tone="u.user_status === 'active' ? 'mint' : 'gray'" :text="u.user_status === 'active' ? '正常' : '已停用'" />
          </div>
        </div>
      </div>
      <div v-else class="flex items-center gap-2 text-sm text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> 加载中…</div>
    </template>

    <template v-if="data && u">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div v-for="s in [
          { k: '对话', v: u.conversation_qty },
          { k: '任务', v: u.task_qty },
          { k: '模型调用', v: data.llm_requests },
          { k: 'Token', v: data.tokens },
        ]" :key="s.k" class="rounded-lg border border-[var(--cs-line)] px-3 py-2.5">
          <div class="ac-caps">{{ s.k }}</div>
          <div class="mt-1 text-lg font-bold text-white tabular-nums">{{ compact(s.v) }}</div>
        </div>
      </div>
      <dl class="ac-dl mt-5">
        <dt>注册时间</dt>
        <dd class="tabular-nums">{{ formatTime(u.created_time) }}</dd>
        <dt>用户 ID</dt>
        <dd class="font-mono text-[12px]">{{ u.user_id }}</dd>
      </dl>

      <div class="ac-caps mt-6 mb-2">最近任务</div>
      <ul class="overflow-hidden rounded-lg border border-[var(--cs-line)]">
        <li v-for="t in data.recent_tasks" :key="t.task_id" class="border-t border-[var(--cs-line)] first:border-t-0">
          <button type="button" class="flex w-full items-center gap-3 px-3 py-2 text-left text-[13px] hover:bg-[var(--cs-line)]" @click="emit('openTask', t)">
            <span class="min-w-0 flex-1">
              <span class="block truncate font-medium text-white">{{ t.title }}</span>
              <span class="text-[11px] text-slate-500">{{ modeLabel(t.mode) }} · {{ relativeTime(t.created_time) }}</span>
            </span>
            <StatusPill :tone="taskPastel(t.task_status)" :text="taskStatusLabel(t.task_status, t.status_reason)" />
          </button>
        </li>
        <li v-if="!data.recent_tasks.length" class="px-3 py-6 text-center text-[13px] text-slate-400">还没有任务</li>
      </ul>
    </template>

    <template #footer>
      <template v-if="u">
        <span v-if="isMe" class="mr-auto text-[12px] text-slate-400">不能停用自己或取消自己的管理员身份</span>
        <button type="button" class="btn-secondary" :disabled="busy || (isMe && u.is_admin)" @click="toggleAdmin">
          {{ u.is_admin ? '取消管理员' : '设为管理员' }}
        </button>
        <button
          type="button"
          :class="u.user_status === 'active' ? 'btn-danger' : 'btn-primary'"
          :disabled="busy || isMe"
          @click="toggleStatus"
        >
          {{ u.user_status === 'active' ? '停用账号' : '启用账号' }}
        </button>
      </template>
    </template>
  </SideDrawer>
</template>
