<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Info, Loader2, Radar } from 'lucide-vue-next'
import type { SettingField } from '@/api/types'
import AdminPage from '@/components/admin/AdminPage.vue'
import SaveBar from '@/components/admin/SaveBar.vue'
import SettingFieldControl from '@/components/admin/SettingFieldControl.vue'
import { useAdminSettings } from '@/lib/useAdminSettings'
import { useDirtyGuard } from '@/lib/useDirtyGuard'

/**
 * 运行参数：搜索引擎、垂直来源、冷却策略、浏览器与人工接手、任务限额（覆盖 config.yaml，新任务立即生效），
 * 以及只读的部署配置。左侧锚点导航，右侧分节表单，整页一个保存条。
 */
const s = useAdminSettings(['search', 'browser', 'task'])
const route = useRoute()
const dirtyCount = computed(() => s.dirtyKeys.value.length)
useDirtyGuard(dirtyCount)

interface Section {
  id: string
  title: string
  desc: string
  keys?: string[]
  group?: SettingField['group']
}
const SECTIONS: Section[] = [
  { id: 'search', title: '搜索引擎', desc: '通用搜索引擎的顺序与使用策略。被拦截或网络不通的引擎会自动冷却并跳过。', keys: ['search_engines', 'search_strategy', 'search_results_per_query'] },
  { id: 'vertical', title: '垂直来源', desc: '搜索规划智能体可按问题选用的专门来源（百科、论文、代码、公众号等）。', keys: ['search_vertical_sources'] },
  { id: 'cooldown', title: '冷却策略', desc: '引擎被拦截或无法访问后，暂停使用的时长。', keys: ['search_engine_cooldown_s', 'search_unreachable_cooldown_s'] },
  { id: 'browser', title: '浏览器与人工接手', desc: '遇到人机验证时暂停任务，请用户在实时画面中完成验证；系统不会尝试绕过验证。', group: 'browser' },
  { id: 'limits', title: '任务限额', desc: '单个任务的默认上限，对之后新开始的任务生效。上限越高结果越全面，耗时与费用也越高。', group: 'task' },
]
const used = computed(() => new Set(SECTIONS.flatMap((x) => x.keys ?? [])))
function fieldsOf(sec: Section): SettingField[] {
  const all = s.data.value?.fields ?? []
  if (sec.keys) return sec.keys.map((k) => all.find((f) => f.key === k)).filter((f): f is SettingField => !!f)
  return all.filter((f) => f.group === sec.group && !used.value.has(f.key))
}
// 后端新增、未归入上面分节的搜索类参数放到“搜索引擎”末尾
const extraSearch = computed(() => (s.data.value?.fields ?? []).filter((f) => f.group === 'search' && !used.value.has(f.key)))
const nav = computed(() => [
  ...SECTIONS.map((x) => ({ id: x.id, title: x.title, dirty: fieldsOf(x).some((f) => s.dirtyKeys.value.includes(f.key)) })),
  { id: 'deploy', title: '部署配置（只读）', dirty: false },
])

// ---------------------------------------------------------------- 锚点：滚动定位与当前节高亮
const active = ref('search')
let io: IntersectionObserver | null = null
function scrollTo(id: string, smooth = true) {
  document.getElementById(`sec-${id}`)?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
  active.value = id
  history.replaceState(history.state, '', `#${id}`)
}
watch(
  () => s.data.value,
  async (d) => {
    if (!d) return
    await nextTick()
    io?.disconnect()
    const root = document.querySelector('[data-admin-scroll]')
    io = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (vis[0]) active.value = vis[0].target.id.replace('sec-', '')
      },
      { root, rootMargin: '-64px 0px -60% 0px' },
    )
    document.querySelectorAll('[data-sec]').forEach((el) => io!.observe(el))
    const h = route.hash.replace('#', '')
    if (h) scrollTo(h, false)
  },
)
onBeforeUnmount(() => io?.disconnect())
</script>

<template>
  <AdminPage>
    <template #actions>
      <RouterLink :to="{ name: 'admin-diagnose' }" class="btn-secondary"><Radar class="h-4 w-4" /> 检测引擎可用性</RouterLink>
    </template>

    <div v-if="s.loading.value && !s.data.value" class="flex items-center gap-2 text-sm text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> 加载中…</div>
    <div v-else class="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[180px_minmax(0,1fr)]">
      <nav class="hidden lg:sticky lg:top-20 lg:block" aria-label="本页分节">
        <ul class="space-y-0.5 border-l border-[var(--cs-line)]">
          <li v-for="n in nav" :key="n.id">
            <a
              :href="`#${n.id}`"
              class="-ml-px flex items-center gap-2 border-l-2 py-1.5 pl-3 text-[13px] transition-colors"
              :class="active === n.id ? 'border-[var(--cs-ink)] font-semibold text-white' : 'border-transparent text-slate-400 hover:text-white'"
              @click.prevent="scrollTo(n.id)"
            >
              {{ n.title }}
              <span v-if="n.dirty" class="h-1.5 w-1.5 rounded-full bg-[var(--pastel-butter-dot)]" title="有未保存的修改" />
            </a>
          </li>
        </ul>
      </nav>

      <div class="min-w-0 space-y-5">
        <div class="flex gap-2.5 rounded-xl border border-[var(--cs-line)] px-4 py-3 text-[13px] leading-6 text-slate-300">
          <Info class="mt-1 h-4 w-4 shrink-0 text-slate-400" />
          <p>这些参数保存在后台，覆盖 config.yaml 中的同名项，<b class="text-white">无需重启</b>，对之后开始的任务生效。「恢复默认」会删除后台的覆盖值，回到 config.yaml 中的设置。</p>
        </div>

        <section v-for="sec in SECTIONS" :id="`sec-${sec.id}`" :key="sec.id" data-sec class="ac-panel scroll-mt-20">
          <header class="border-b border-[var(--cs-line)] px-5 py-3.5">
            <h2 class="text-[15px] font-semibold text-white">{{ sec.title }}</h2>
            <p class="mt-0.5 text-[12px] text-slate-400">{{ sec.desc }}</p>
          </header>
          <SettingFieldControl
            v-for="f in [...fieldsOf(sec), ...(sec.id === 'search' ? extraSearch : [])]"
            :key="f.key"
            v-model="s.drafts[f.key]"
            :field="f"
            :dirty="s.dirtyKeys.value.includes(f.key)"
            @reset="s.reset(f.key)"
          />
        </section>

        <section id="sec-deploy" data-sec class="ac-panel scroll-mt-20">
          <header class="border-b border-[var(--cs-line)] px-5 py-3.5">
            <h2 class="text-[15px] font-semibold text-white">部署配置（只读）</h2>
            <p class="mt-0.5 text-[12px] text-slate-400">
              以下项在 config.yaml 中修改，重启服务后生效：
              <code class="rounded bg-[var(--cs-code-bg)] px-1.5 py-0.5 font-mono text-[11px]">{{ s.data.value?.config_path }}</code>
            </p>
          </header>
          <div class="grid gap-x-8 gap-y-5 px-5 py-4 md:grid-cols-2 xl:grid-cols-3">
            <div v-for="g in s.data.value?.static ?? []" :key="g.group">
              <div class="ac-caps mb-2">{{ g.group }}</div>
              <dl class="space-y-1.5 text-[13px]">
                <div v-for="it in g.items" :key="it.label" class="flex gap-3">
                  <dt class="w-28 shrink-0 text-slate-400">{{ it.label }}</dt>
                  <dd class="min-w-0 flex-1 truncate font-mono text-[12px] leading-5 text-slate-200" :title="it.value">{{ it.value }}</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>
      </div>
    </div>

    <SaveBar :count="dirtyCount" :saving="s.saving.value" @save="s.save()" @discard="s.discard()" />
  </AdminPage>
</template>
