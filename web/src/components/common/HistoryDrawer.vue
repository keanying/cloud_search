<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Archive, MessageSquare, Search, Trash2, X } from 'lucide-vue-next'
import { api } from '@/api/client'
import { useConversationsStore } from '@/stores/conversations'
import { useToastStore } from '@/stores/toast'
import { relativeTime } from '@/lib/format'
import EmptyState from './EmptyState.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const store = useConversationsStore()
const toast = useToastStore()
const router = useRouter()
const q = ref('')
const searchEl = ref<HTMLInputElement | null>(null)

const filtered = computed(() => {
  const k = q.value.trim().toLowerCase()
  return store.items.filter((c) => c.conversation_status !== 'deleted' && (!k || c.title.toLowerCase().includes(k)))
})

watch(
  () => props.open,
  (o) => {
    if (o) {
      void store.refresh().catch((e) => toast.error(e))
      setTimeout(() => searchEl.value?.focus(), 50)
    }
  },
)
onMounted(() => {
  if (props.open) void store.refresh()
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
  } catch (e) {
    toast.error(e)
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex justify-end" @keydown.escape="emit('close')">
      <div class="absolute inset-0 bg-black/40" @click="emit('close')" />
      <aside class="glass-strong relative flex h-full w-full max-w-sm flex-col !rounded-none sm:!rounded-l-[28px]" aria-label="最近对话">
        <header class="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h2 class="text-base font-semibold">最近对话</h2>
          <button class="icon-btn" aria-label="关闭" @click="emit('close')"><X class="h-4 w-4" /></button>
        </header>
        <div class="px-4 py-3">
          <label class="relative block">
            <span class="sr-only">搜索对话</span>
            <Search class="absolute top-2.5 left-3 h-4 w-4 text-slate-500" />
            <input ref="searchEl" v-model="q" class="input !rounded-full pl-9" placeholder="按标题搜索" />
          </label>
        </div>
        <div class="flex-1 overflow-y-auto px-2 pb-4">
          <EmptyState v-if="store.loaded && !filtered.length" :title="q ? '没有匹配的对话' : '还没有对话'" desc="在首页输入问题即可开始" />
          <ul>
            <li v-for="c in filtered" :key="c.conversation_id" class="group">
              <div class="flex items-center gap-2 rounded-2xl px-2.5 py-2.5 hover:bg-white/5">
                <button class="flex min-w-0 flex-1 items-center gap-2 text-left" @click="go(c.conversation_id)">
                  <MessageSquare class="h-4 w-4 shrink-0 text-slate-400" />
                  <span class="min-w-0 flex-1">
                    <span class="block truncate text-sm text-slate-100">{{ c.title }}</span>
                    <span class="block text-xs text-slate-500">
                      {{ relativeTime(c.updated_time) }}
                      <template v-if="c.active_task_qty"> · {{ c.active_task_qty }} 个任务进行中</template>
                      <template v-if="c.conversation_status === 'archived'"> · 已归档</template>
                    </span>
                  </span>
                </button>
                <button
                  v-if="c.conversation_status !== 'archived'"
                  class="icon-btn opacity-0 group-hover:opacity-100 focus:opacity-100"
                  aria-label="归档对话"
                  title="归档"
                  @click="archive(c.conversation_id)"
                >
                  <Archive class="h-4 w-4" />
                </button>
                <button
                  class="icon-btn opacity-0 group-hover:opacity-100 focus:opacity-100"
                  aria-label="删除对话"
                  title="删除"
                  @click="remove(c.conversation_id)"
                >
                  <Trash2 class="h-4 w-4" />
                </button>
              </div>
            </li>
          </ul>
          <div v-if="store.nextCursor" class="px-2 pt-2">
            <button class="btn-ghost w-full" :disabled="store.loading" @click="store.loadMore()">加载更多</button>
          </div>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
