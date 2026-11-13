<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Archive, PanelLeftClose, Plus, Search, Trash2, X } from 'lucide-vue-next'
import type { ConversationOut } from '@/api/types'
import { api } from '@/api/client'
import { parseTime, relativeTime } from '@/lib/format'
import { useConversationsStore } from '@/stores/conversations'
import { useToastStore } from '@/stores/toast'

/** 左侧对话列表：新对话、搜索、按今天/最近7天/更早分组 */
const props = defineProps<{ currentId?: string | null; drawer?: boolean }>()
const emit = defineEmits<{ collapse: []; close: [] }>()
const store = useConversationsStore()
const toast = useToastStore()
const router = useRouter()
const q = ref('')

onMounted(() => {
  if (!store.loaded) void store.refresh().catch((e) => toast.error(e))
})

const groups = computed(() => {
  const k = q.value.trim().toLowerCase()
  const list = store.items.filter((c) => c.conversation_status !== 'deleted' && (!k || c.title.toLowerCase().includes(k)))
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)
  const t0 = startOfToday.getTime()
  const week = t0 - 6 * 86400_000
  const out: { label: string; items: ConversationOut[] }[] = [
    { label: '今天', items: [] },
    { label: '最近 7 天', items: [] },
    { label: '更早', items: [] },
  ]
  for (const c of list) {
    const t = parseTime(c.updated_time)?.getTime() ?? 0
    out[t >= t0 ? 0 : t >= week ? 1 : 2].items.push(c)
  }
  return out.filter((g) => g.items.length)
})

function go(id: string) {
  emit('close')
  router.push({ name: 'chat', params: { id } })
}

async function archive(id: string) {
  try {
    store.upsert(await api.patchConversation(id, { conversation_status: 'archived' }))
    toast.push('已归档；后台任务不受影响', 'success')
  } catch (e) {
    toast.error(e)
  }
}

async function remove(id: string) {
  if (!confirm('删除该对话？只隐藏聊天记录，不会停止已关联的后台任务，也不删除已生成文件。')) return
  try {
    await api.deleteConversation(id)
    store.remove(id)
    if (id === props.currentId) router.push({ name: 'home' })
  } catch (e) {
    toast.error(e)
  }
}
</script>

<template>
  <aside class="flex min-h-0 flex-col" aria-label="对话列表">
    <div class="flex items-center gap-2 px-1 pb-3">
      <RouterLink to="/" class="btn-primary flex-1 !py-2.5" @click="emit('close')">
        <Plus class="h-4 w-4" /> 新对话
      </RouterLink>
      <button v-if="drawer" class="round-btn-light" aria-label="关闭对话列表" @click="emit('close')">
        <X class="h-4 w-4" />
      </button>
      <button v-else class="round-btn-light" aria-label="收起对话列表" title="收起" @click="emit('collapse')">
        <PanelLeftClose class="h-4 w-4" />
      </button>
    </div>
    <label class="relative mx-1 mb-3 block">
      <span class="sr-only">搜索对话</span>
      <Search class="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-slate-500" />
      <input v-model="q" class="input !rounded-full !py-2 pl-10" placeholder="搜索对话" />
    </label>
    <div class="-mx-1 min-h-0 flex-1 overflow-y-auto px-1 pb-2">
      <p v-if="store.loaded && !groups.length" class="px-3 py-6 text-center text-sm text-slate-500">
        {{ q ? '没有匹配的对话' : '还没有对话，点上方“新对话”开始' }}
      </p>
      <section v-for="g in groups" :key="g.label" class="mb-3">
        <h3 class="px-3 pb-1 text-xs font-semibold tracking-normal text-slate-500">{{ g.label }}</h3>
        <ul>
          <li v-for="c in g.items" :key="c.conversation_id" class="group relative">
            <button
              class="flex w-full items-center gap-2.5 rounded-2xl px-3 py-2.5 text-left transition-colors"
              :class="c.conversation_id === currentId ? 'surface !rounded-2xl !shadow-none' : 'hover:bg-white/5'"
              :aria-current="c.conversation_id === currentId ? 'page' : undefined"
              @click="go(c.conversation_id)"
            >
              <span
                class="h-2 w-2 shrink-0 rounded-full"
                :class="
                  c.active_task_qty
                    ? 'cs-ping bg-brand-500 text-brand-500'
                    : c.conversation_status === 'archived'
                      ? 'bg-slate-600'
                      : 'border border-slate-500'
                "
                :title="c.active_task_qty ? `${c.active_task_qty} 个任务进行中` : c.conversation_status === 'archived' ? '已归档' : '空闲'"
                aria-hidden="true"
              />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-medium text-slate-100">{{ c.title }}</span>
                <span class="block text-xs text-slate-500">
                  {{ relativeTime(c.updated_time) }}
                  <template v-if="c.active_task_qty"> · 执行中</template>
                  <template v-if="c.conversation_status === 'archived'"> · 已归档</template>
                </span>
              </span>
            </button>
            <div class="absolute top-1/2 right-2 hidden -translate-y-1/2 items-center gap-0.5 group-focus-within:flex group-hover:flex">
              <button
                v-if="c.conversation_status !== 'archived'"
                class="icon-btn !h-7 !w-7"
                style="background: var(--cs-surface-solid)"
                aria-label="归档对话"
                title="归档"
                @click.stop="archive(c.conversation_id)"
              >
                <Archive class="h-3.5 w-3.5" />
              </button>
              <button
                class="icon-btn !h-7 !w-7"
                style="background: var(--cs-surface-solid)"
                aria-label="删除对话"
                title="删除"
                @click.stop="remove(c.conversation_id)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </button>
            </div>
          </li>
        </ul>
      </section>
      <div v-if="store.nextCursor" class="px-2 pt-1">
        <button class="btn-ghost btn-sm w-full" :disabled="store.loading" @click="store.loadMore()">加载更多</button>
      </div>
    </div>
  </aside>
</template>
