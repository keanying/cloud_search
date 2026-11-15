<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CornerDownLeft, ListChecks, Loader2, Search, User } from 'lucide-vue-next'
import type { AdminTask, AdminUser } from '@/api/types'
import { api } from '@/api/client'
import { ADMIN_ITEMS } from '@/lib/adminNav'
import { taskStatusLabel } from '@/lib/format'

/** 命令面板（⌘K / Ctrl+K）：跳转后台页面，搜索任务与用户（打开详情抽屉） */
const open = defineModel<boolean>({ default: false })
const router = useRouter()
const q = ref('')
const input = ref<HTMLInputElement | null>(null)
const tasks = ref<AdminTask[]>([])
const users = ref<AdminUser[]>([])
const searching = ref(false)
const active = ref(0)

interface Item {
  kind: 'page' | 'task' | 'user'
  id: string
  title: string
  sub: string
  run: () => void
}

const pages = computed<Item[]>(() => {
  const k = q.value.trim().toLowerCase()
  return ADMIN_ITEMS.filter((p) => !k || `${p.label} ${p.desc} ${p.keywords ?? ''} ${p.group ?? ''}`.toLowerCase().includes(k)).map(
    (p) => ({
      kind: 'page',
      id: p.name,
      title: p.label,
      sub: p.group ?? '管理后台',
      run: () => void router.push({ name: p.name }),
    }),
  )
})
const items = computed<Item[]>(() => [
  ...pages.value,
  ...tasks.value.map<Item>((t) => ({
    kind: 'task',
    id: t.task_id,
    title: t.title,
    sub: `${taskStatusLabel(t.task_status, t.status_reason)} · ${t.display_name || t.username || ''}`,
    run: () => void router.push({ name: 'admin-tasks', query: { task: t.task_id } }),
  })),
  ...users.value.map<Item>((u) => ({
    kind: 'user',
    id: u.user_id,
    title: u.display_name || u.username,
    sub: `@${u.username}${u.is_admin ? ' · 管理员' : ''}`,
    run: () => void router.push({ name: 'admin-users', query: { user: u.user_id } }),
  })),
])

let timer: number | undefined
let seq = 0
watch(q, (v) => {
  active.value = 0
  window.clearTimeout(timer)
  const k = v.trim()
  if (!k) {
    tasks.value = []
    users.value = []
    return
  }
  timer = window.setTimeout(async () => {
    const my = ++seq
    searching.value = true
    try {
      const [t, u] = await Promise.all([
        api.adminTasks({ q: k, page: 1, size: 5 }).catch(() => ({ items: [] as AdminTask[] })),
        api.adminUsers({ q: k, page: 1, size: 5 }).catch(() => ({ items: [] as AdminUser[] })),
      ])
      if (my !== seq) return
      tasks.value = t.items
      users.value = u.items
    } finally {
      if (my === seq) searching.value = false
    }
  }, 250)
})

watch(open, async (v) => {
  if (v) {
    q.value = ''
    active.value = 0
    await nextTick()
    input.value?.focus()
  }
})
onBeforeUnmount(() => window.clearTimeout(timer))

function choose(it: Item | undefined) {
  if (!it) return
  open.value = false
  it.run()
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = Math.min(items.value.length - 1, active.value + 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = Math.max(0, active.value - 1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    choose(items.value[active.value])
  } else if (e.key === 'Escape') {
    open.value = false
  }
}
const sections = computed(() => {
  const out: { title: string; items: { it: Item; idx: number }[] }[] = []
  const label = { page: '页面', task: '任务', user: '用户' } as const
  items.value.forEach((it, idx) => {
    const t = label[it.kind]
    let s = out.find((x) => x.title === t)
    if (!s) out.push((s = { title: t, items: [] }))
    s.items.push({ it, idx })
  })
  return out
})
</script>

<template>
  <Teleport to="body">
    <Transition name="cp">
      <div v-if="open" class="fixed inset-0 z-[950] flex items-start justify-center px-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="命令面板">
        <div class="cp-mask absolute inset-0" @click="open = false" />
        <div class="cp-box relative w-full max-w-[600px] overflow-hidden">
          <div class="flex items-center gap-2.5 border-b border-[var(--cs-line)] px-4">
            <Search class="h-4 w-4 shrink-0 text-slate-400" />
            <input
              ref="input"
              v-model="q"
              class="h-12 min-w-0 flex-1 bg-transparent text-[15px] text-white outline-none placeholder:text-slate-500"
              placeholder="搜索页面、任务、用户…"
              aria-label="搜索页面、任务、用户"
              @keydown="onKey"
            />
            <Loader2 v-if="searching" class="h-4 w-4 animate-spin text-slate-400" />
            <span class="ac-kbd">Esc</span>
          </div>
          <div class="max-h-[56vh] overflow-y-auto p-2">
            <template v-for="s in sections" :key="s.title">
              <div class="px-2.5 pt-2 pb-1 text-[11px] font-semibold text-slate-400">{{ s.title }}</div>
              <button
                v-for="{ it, idx } in s.items"
                :key="`${it.kind}-${it.id}`"
                type="button"
                class="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left"
                :class="idx === active ? 'bg-[var(--cs-line)]' : ''"
                @mouseenter="active = idx"
                @click="choose(it)"
              >
                <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--cs-line)] text-slate-400">
                  <component :is="ADMIN_ITEMS.find((p) => p.name === it.id)?.icon" v-if="it.kind === 'page'" class="h-3.5 w-3.5" />
                  <ListChecks v-else-if="it.kind === 'task'" class="h-3.5 w-3.5" />
                  <User v-else class="h-3.5 w-3.5" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-[13px] font-medium text-white">{{ it.title }}</span>
                  <span class="block truncate text-[11px] text-slate-500">{{ it.sub }}</span>
                </span>
                <CornerDownLeft v-if="idx === active" class="h-3.5 w-3.5 text-slate-400" />
              </button>
            </template>
            <div v-if="!items.length" class="px-3 py-8 text-center text-sm text-slate-400">
              {{ searching ? '搜索中…' : '没有匹配的页面、任务或用户' }}
            </div>
          </div>
          <div class="flex items-center gap-3 border-t border-[var(--cs-line)] px-4 py-2 text-[11px] text-slate-500">
            <span><span class="ac-kbd">↑</span> <span class="ac-kbd">↓</span> 选择</span>
            <span><span class="ac-kbd">Enter</span> 打开</span>
            <span class="ml-auto">任务与用户按标题、用户名搜索</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cp-mask {
  background: rgb(20 22 45 / 0.3);
  backdrop-filter: blur(3px);
}
.cp-box {
  border-radius: 24px;
  border: 1px solid var(--cs-rim);
  background: var(--cs-surface-solid);
  box-shadow: var(--cs-shadow-lg);
  backdrop-filter: var(--cs-blur);
  -webkit-backdrop-filter: var(--cs-blur);
}
.cp-enter-active,
.cp-leave-active {
  transition: opacity 0.15s ease;
}
.cp-enter-from,
.cp-leave-to {
  opacity: 0;
}
</style>
