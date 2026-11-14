<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { AdminUser } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import TableToolbar from '@/components/admin/TableToolbar.vue'
import TaskDrawer from '@/components/admin/TaskDrawer.vue'
import UserDrawer from '@/components/admin/UserDrawer.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import { hueTone } from '@/lib/adminFormat'
import { formatTime } from '@/lib/format'
import { useColumnPrefs } from '@/lib/useColumnPrefs'
import { useServerTable } from '@/lib/useServerTable'
import { useAuthStore } from '@/stores/auth'

/** 用户：点行打开详情抽屉（用量、最近任务、权限与停用操作）；地址栏 ?user= 可直达 */
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const t = useServerTable<AdminUser, { q: string }>((q) => api.adminUsers(q), { q: '' })

const all: Column[] = [
  { key: 'username', title: '用户', minWidth: 240, fixed: 'left', width: 280 },
  { key: 'role', title: '角色', width: 100 },
  { key: 'user_status', title: '状态', width: 100 },
  { key: 'conversation_qty', title: '对话', width: 80, align: 'right', sortable: true },
  { key: 'task_qty', title: '任务', width: 80, align: 'right', sortable: true },
  { key: 'created_time', title: '注册时间', width: 160, sortable: true },
]
const cols = useColumnPrefs('admin-users', all)
const openId = computed(() => (typeof route.query.user === 'string' ? route.query.user : null))
function openUser(id: string | null) {
  void router.replace({ query: { ...route.query, user: id || undefined } })
}
function onUpdated(u: AdminUser) {
  t.rows.value = t.rows.value.map((x) => (x.user_id === u.user_id ? u : x))
}
const taskOpen = ref<string | null>(null)
</script>

<template>
  <AdminPage>
    <TableToolbar
      v-model:q="t.filters.q"
      v-model:hidden="cols.hidden.value"
      v-model:density="cols.density.value"
      placeholder="搜索用户名或昵称"
      :loading="t.loading.value"
      :toggleable="cols.toggleable.value"
      @refresh="t.reload()"
    />
    <DataTable
      v-model:page="t.page.value"
      v-model:size="t.size.value"
      :columns="cols.visible.value"
      :rows="t.rows.value"
      row-key="user_id"
      :total="t.total.value"
      :loading="t.loading.value"
      :density="cols.density.value"
      :active-key="openId"
      row-clickable
      empty-text="没有找到用户"
      @row-click="(r: AdminUser) => openUser(r.user_id)"
    >
      <template #cell-username="{ row }">
        <span class="flex items-center gap-2.5">
          <span
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold"
            :style="{ background: `var(--pastel-${hueTone(row.username)})`, color: `var(--pastel-${hueTone(row.username)}-ink)` }"
          >{{ (row.display_name || row.username).slice(0, 1).toUpperCase() }}</span>
          <span class="min-w-0 leading-tight">
            <span class="block truncate font-medium text-white">
              {{ row.display_name || row.username }}
              <span v-if="row.user_id === auth.user?.user_id" class="ml-1 text-[11px] font-normal text-slate-400">（你）</span>
            </span>
            <span class="block truncate font-mono text-[11px] text-slate-500">@{{ row.username }}</span>
          </span>
        </span>
      </template>
      <template #cell-role="{ row }">
        <StatusPill v-if="row.is_admin" tone="lilac" text="管理员" />
        <span v-else class="text-[12px] text-slate-400">成员</span>
      </template>
      <template #cell-user_status="{ row }">
        <StatusPill :tone="row.user_status === 'active' ? 'mint' : 'gray'" :text="row.user_status === 'active' ? '正常' : '已停用'" />
      </template>
      <template #cell-conversation_qty="{ row }"><span class="tabular-nums">{{ row.conversation_qty }}</span></template>
      <template #cell-task_qty="{ row }"><span class="tabular-nums">{{ row.task_qty }}</span></template>
      <template #cell-created_time="{ row }"><span class="text-slate-300 tabular-nums">{{ formatTime(row.created_time) }}</span></template>
    </DataTable>
    <p class="mt-2 px-1 text-[12px] text-slate-500">排序只作用于当前页。不能取消自己的管理员身份；至少保留一个管理员。</p>

    <UserDrawer :user-id="openId" @close="openUser(null)" @updated="onUpdated" @open-task="(tk) => (taskOpen = tk.task_id)" />
    <TaskDrawer :task-id="taskOpen" @close="taskOpen = null" />
  </AdminPage>
</template>
