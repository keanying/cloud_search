<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { BookOpen, Database, FileBarChart, FileText, MessageSquare, Search } from 'lucide-vue-next'
import type { ArtifactOut, ModeSelection } from '@/api/types'
import { api } from '@/api/client'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { artifactKindLabel, relativeTime } from '@/lib/format'
import { useChatStore } from '@/stores/chat'
import { useConversationsStore } from '@/stores/conversations'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const chat = useChatStore()
const convs = useConversationsStore()
const panel = usePanelStore()
const toast = useToastStore()

const text = ref('')
const mode = ref<ModeSelection>((localStorage.getItem('cs_default_mode') as ModeSelection) || 'auto')
const sending = ref(false)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
const artifacts = ref<ArtifactOut[]>([])
const artifactsLoaded = ref(false)


/** 快捷建议只填入输入框并切换模式，不会自动发送 */
const suggestions: { label: string; icon: typeof Search; mode: ModeSelection; text: string }[] = [
  { label: '搜索问题', icon: Search, mode: 'quick_search', text: '帮我查一下：' },
  { label: '深入研究', icon: BookOpen, mode: 'research', text: '帮我研究一下这个主题，并生成带引用的报告：' },
  { label: '采集数据', icon: Database, mode: 'dataset', text: '帮我采集以下数据并整理成 CSV：' },
  { label: '生成报告', icon: FileBarChart, mode: 'hybrid', text: '帮我采集相关数据并生成分析报告：' },
]

function applySuggestion(s: (typeof suggestions)[number]) {
  text.value = s.text
  mode.value = s.mode
  composer.value?.focus()
}

onMounted(async () => {
  chat.close()
  panel.reset()
  void convs.refresh().catch(() => {})
  try {
    artifacts.value = (await api.listArtifacts()).slice(0, 4)
  } catch {
    /* 空态 */
  } finally {
    artifactsLoaded.value = true
  }
})

async function submit() {
  const t = text.value.trim()
  if (!t || sending.value) return
  sending.value = true
  try {
    const conv = await api.createConversation()
    convs.upsert(conv)
    await chat.open(conv.conversation_id)
    await chat.send(t, mode.value)
    text.value = ''
    router.push({ name: 'chat', params: { id: conv.conversation_id } })
  } catch (e) {
    // 发送失败时保留输入内容，不显示伪成功
    toast.error(e, '发送失败，输入内容已保留')
  } finally {
    sending.value = false
  }
}

const recent = computed(() => convs.items.filter((c) => c.conversation_status === 'active').slice(0, 4))
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto flex min-h-full max-w-5xl flex-col items-center px-4 pt-[12vh] pb-10">
      <h1 class="text-center text-3xl font-semibold tracking-wide text-white md:text-4xl">你好，今天想探索什么？</h1>
      <p class="mt-3 text-center text-sm text-slate-400 md:text-base">从一个问题开始，让 AI 帮你搜索、整理数据、生成报告</p>

      <div class="mt-8 w-full max-w-[760px]">
        <ChatComposer
          ref="composer"
          v-model="text"
          v-model:mode="mode"
          variant="home"
          :sending="sending"
          placeholder="描述你的问题，或告诉我想采集哪些数据…"
          @submit="submit"
        />
        <div class="mt-4 flex flex-wrap justify-center gap-2">
          <button v-for="s in suggestions" :key="s.label" type="button" class="chip" @click="applySuggestion(s)">
            <component :is="s.icon" class="h-4 w-4 text-brand-300" /> {{ s.label }}
          </button>
        </div>
      </div>

      <div class="mt-14 grid w-full max-w-[880px] gap-4 md:grid-cols-2">
        <section class="glass p-4">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="card-title"><MessageSquare class="h-4 w-4 text-brand-300" /> 最近对话</h2>
          </div>
          <EmptyState v-if="convs.loaded && !recent.length" title="还没有对话" desc="输入第一个问题开始吧" />
          <ul v-else class="space-y-1">
            <li v-for="c in recent" :key="c.conversation_id">
              <RouterLink :to="{ name: 'chat', params: { id: c.conversation_id } }" class="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/5">
                <span class="min-w-0 flex-1 truncate text-sm text-slate-200">{{ c.title }}</span>
                <span v-if="c.active_task_qty" class="text-xs text-brand-300">进行中</span>
                <span class="shrink-0 text-xs text-slate-500">{{ relativeTime(c.updated_time) }}</span>
              </RouterLink>
            </li>
          </ul>
        </section>
        <section class="glass p-4">
          <div class="mb-2 flex items-center justify-between">
            <h2 class="card-title"><FileText class="h-4 w-4 text-brand-300" /> 我的成果</h2>
            <RouterLink v-if="artifacts.length" to="/artifacts" class="text-xs text-slate-400 hover:text-white">全部</RouterLink>
          </div>
          <EmptyState v-if="artifactsLoaded && !artifacts.length" title="你的数据和报告会出现在这里" />
          <ul v-else class="space-y-1">
            <li v-for="a in artifacts" :key="a.artifact_id">
              <RouterLink to="/artifacts" class="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/5">
                <span class="min-w-0 flex-1 truncate text-sm text-slate-200">{{ a.display_name }}</span>
                <span class="shrink-0 text-xs text-slate-500">{{ artifactKindLabel(a.artifact_kind) }}</span>
              </RouterLink>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>
