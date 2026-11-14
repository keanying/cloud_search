<script setup lang="ts">
import { ref } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import type { AdminUser } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import ToggleSwitch from '@/components/common/ToggleSwitch.vue'
import { hueTone } from '@/lib/adminFormat'
import { formatTime } from '@/lib/format'
import { useServerTable } from '@/lib/useServerTable'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

const auth = useAuthStore()
const toast = useToastStore()
const t = useServerTable<AdminUser, { q: string }>((q) => api.adminUsers(q), { q: '' })
const busy = ref<string | null>(null)

const columns: Column[] = [
  { key: 'username', title: '用户', minWidth: 240, fixed: 'left', width: 280 },
  { key: 'is_admin', title: '管理员', width: 110, align: 'center' },
  { key: 'user_status', title: '状态', width: 120 },
  { key: 'conversation_qty', title: '对话', width: 90, align: 'right', sortable: true },
  { key: 'task_qty', title: '任务', width: 90, align: 'right', sortable: true },
  { key: 'created_time', title: '注册时间', width: 170, sortable: true },
  { key: 'actions', title: '操作', width: 120, align: 'right' },
]

function replace(u: AdminUser) {
  t.rows.value = t.rows.value.map((x) => (x.user_id === u.user_id ? u : x))
}

async function setAdmin(u: AdminUser, v: boolean) {
  const name = u.display_name || u.username
  if (!confirm(v ? `将「${name}」设为管理员？管理员可以修改模型密钥和全局配置。` : `取消「${name}」的管理员权限？`)) return
  busy.value = u.user_id
  try {
    replace(await api.patchAdminUser(u.user_id, { is_admin: v }))
    toast.push('已更新', 'success')
  } catch (e) {
    toast.error(e)
  } finally {
    busy.value = null
  }
}
async function setStatus(u: AdminUser) {
  const next = u.user_status === 'active' ? 'disabled' : 'active'
  const name = u.display_name || u.username
  if (next === 'disabled' && !confirm(`停用「${name}」？停用后该账号无法登录，已有任务不受影响。`)) return
  busy.value = u.user_id
  try {
    replace(await api.patchAdminUser(u.user_id, { user_status: next }))
    toast.push(next === 'disabled' ? '已停用' : '已启用', 'success')
  } catch (e) {
    toast.error(e)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <AdminPage>
    <template #actions>
      <button class="btn-secondary btn-sm" :disabled="t.loading.value" @click="t.reload()">
        <RefreshCw class="h-3.5 w-3.5" :class="t.loading.value ? 'animate-spin' : ''" /> 刷新
      </button>
    </template>
    <FilterBar v-model:q="t.filters.q" placeholder="搜索用户名或昵称" />
    <DataTable
      v-model:page="t.page.value"
      v-model:size="t.size.value"
      :columns="columns"
      :rows="t.rows.value"
      row-key="user_id"
      :total="t.total.value"
      :loading="t.loading.value"
      empty-text="没有找到用户"
    >
      <template #cell-username="{ row }">
        <span class="flex items-center gap-3">
          <span
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl text-sm font-bold"
            :style="{ background: `var(--pastel-${hueTone(row.username)})`, color: `var(--pastel-${hueTone(row.username)}-ink)` }"
          >
            {{ (row.display_name || row.username).slice(0, 1).toUpperCase() }}
          </span>
          <span class="min-w-0 leading-tight">
            <span class="block truncate font-semibold text-white">
              {{ row.display_name || row.username }}
              <span v-if="row.user_id === auth.user?.user_id" class="ml-1 text-[11px] font-medium text-slate-400">（你）</span>
            </span>
            <span class="block truncate font-mono text-[11px] text-slate-500">@{{ row.username }}</span>
          </span>
        </span>
      </template>
      <template #cell-is_admin="{ row }">
        <ToggleSwitch
          small
          :model-value="row.is_admin"
          :disabled="busy === row.user_id"
          :label="`${row.username} 管理员`"
          @update:model-value="(v: boolean) => setAdmin(row, v)"
        />
      </template>
      <template #cell-user_status="{ row }">
        <StatusPill :tone="row.user_status === 'active' ? 'mint' : 'gray'" :text="row.user_status === 'active' ? '正常' : '已停用'" />
      </template>
      <template #cell-conversation_qty="{ row }"><span class="tabular-nums">{{ row.conversation_qty }}</span></template>
      <template #cell-task_qty="{ row }"><span class="tabular-nums">{{ row.task_qty }}</span></template>
      <template #cell-created_time="{ row }"><span class="text-slate-300 tabular-nums">{{ formatTime(row.created_time) }}</span></template>
      <template #cell-actions="{ row }">
        <button
          class="btn-sm"
          :class="row.user_status === 'active' ? 'btn-ghost' : 'btn-secondary'"
          :disabled="busy === row.user_id"
          @click="setStatus(row)"
        >
          {{ row.user_status === 'active' ? '停用' : '启用' }}
        </button>
      </template>
    </DataTable>
  </AdminPage>
</template>
