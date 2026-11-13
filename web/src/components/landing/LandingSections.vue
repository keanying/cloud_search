<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  ArrowRight,
  BookOpenCheck,
  ChevronDown,
  Database,
  FileCheck2,
  GraduationCap,
  Landmark,
  Lock,
  MapPinned,
  MessageSquareText,
  Radar,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from 'lucide-vue-next'
import type { ModeSelection } from '@/api/types'
import { vReveal } from '@/lib/reveal'
import LandingFeatures from './LandingFeatures.vue'
import LandingMockup from './LandingMockup.vue'

defineProps<{ loggedIn: boolean }>()
const emit = defineEmits<{ try: [mode: ModeSelection, text: string]; start: [] }>()

function go(id: string) {
  document.getElementById(id)?.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'start',
  })
}

// ---------------------------------------------------------------- 工作方式
const STEPS = [
  { icon: MessageSquareText, title: '说出需求', desc: '用一句话描述问题、想要的数据或报告，也可以选择模式。' },
  { icon: Search, title: '规划搜索', desc: '理解真实意图，优化搜索词，选择合适的引擎与站内来源。' },
  { icon: BookOpenCheck, title: '浏览 · 读取 · 核验', desc: '在云端浏览器真实打开网页，抽取信息并逐字核对原文。' },
  { icon: FileCheck2, title: '交付成果', desc: '带引用的回答、Word / PDF 报告、带字段说明的 Excel 数据。' },
]

// ---------------------------------------------------------------- 使用场景
interface Scenario {
  key: string
  label: string
  icon: typeof Search
  desc: string
  mode: ModeSelection
  modeLabel: string
  prompt: string
}
const SCENARIOS: Scenario[] = [
  { key: 'industry', label: '行业研究', icon: TrendingUp, mode: 'research', modeLabel: '深入研究',
    desc: '多角度梳理行业现状、主要参与者与趋势，输出带引用的研究报告。',
    prompt: '研究一下国内储能行业 2026 年的发展现状、主要企业和政策支持，生成带引用的报告' },
  { key: 'data', label: '数据采集', icon: Database, mode: 'dataset', modeLabel: '采集数据',
    desc: '按你定义的字段采集结构化数据，缺失值注明原因，导出 Excel。',
    prompt: '采集北京市主要博物馆的名称、地址、开放时间、是否需要预约、门票价格，整理成表格' },
  { key: 'competitor', label: '竞品监测', icon: Radar, mode: 'hybrid', modeLabel: '数据+报告',
    desc: '汇总竞品的产品、价格与近期动态，数据表与对比分析一起交付。',
    prompt: '对比国内三家主流云盘产品的套餐价格、存储空间和近期功能更新，做成表格并写分析' },
  { key: 'policy', label: '政策跟踪', icon: Landmark, mode: 'quick_search', modeLabel: '搜索问题',
    desc: '优先查找政府网站等官方来源，给出带出处的最新要点。',
    prompt: '查一下今年个人所得税专项附加扣除有哪些调整，只看官方来源' },
  { key: 'academic', label: '学术调研', icon: GraduationCap, mode: 'research', modeLabel: '深入研究',
    desc: '检索论文与权威资料，梳理研究脉络与代表性工作。',
    prompt: '调研检索增强生成（RAG）在长文档问答上的主要方法和最新论文，整理成综述' },
  { key: 'travel', label: '出行攻略', icon: MapPinned, mode: 'quick_search', modeLabel: '搜索问题',
    desc: '整合景点开放时间、预约规则与交通信息，出发前心里有数。',
    prompt: '周末带孩子去故宫，帮我查开放时间、预约方式和推荐参观路线' },
]
const activeIdx = ref(0)
const active = computed(() => SCENARIOS[activeIdx.value])
const tabRefs = ref<HTMLButtonElement[]>([])
function onTabKey(e: KeyboardEvent) {
  const n = SCENARIOS.length
  let i = activeIdx.value
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') i = (i + 1) % n
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') i = (i - 1 + n) % n
  else if (e.key === 'Home') i = 0
  else if (e.key === 'End') i = n - 1
  else return
  e.preventDefault()
  activeIdx.value = i
  tabRefs.value[i]?.focus()
}

// ---------------------------------------------------------------- 安全可信
const TRUST = [
  { title: '内容来自真实读取的网页', desc: '回答依据云端浏览器实际打开的页面，摘录逐字核对原文，对不上的不采用。' },
  { title: '图表不编数据', desc: '图表中的每个数字都必须能在来源或程序计算结果中找到，否则不画。' },
  { title: '人工接管不经过 AI', desc: '你在实时画面里的输入直接进入网页，不发给 AI，接管期间的画面也不保存。' },
  { title: '密钥加密保存', desc: '大模型 API Key 加密存储，前端和智能体都看不到明文。' },
  { title: '可私有部署', desc: '可部署在自己的服务器上，数据库、文件与浏览器都在你的环境里。' },
]

// ---------------------------------------------------------------- 大模型
const MODELS = ['OpenAI', 'DeepSeek', 'Kimi', '火山方舟（豆包）', '通义千问', '智谱', '任意 OpenAI 兼容接口']

// ---------------------------------------------------------------- 常见问题
const FAQ = [
  { q: '需要自己准备搜索 API 吗？',
    a: '不需要。系统用云端浏览器直接打开搜索引擎（默认 DuckDuckGo，备用 Google、必应、百度、搜狗）和各网站的站内搜索，读取真实网页。只需要配置大模型。' },
  { q: '搜索时遇到验证码或登录页怎么办？',
    a: 'AI 会暂停，并在对话里请你协助。点「接手处理」后，你可以在右侧实时画面中直接操作网页，完成后点「交还给 AI」继续；如果没人处理，到时间会自动跳过并换用其他来源，系统不会尝试破解验证。' },
  { q: '结果可靠吗？怎么核对？',
    a: '每个事实句都标注来源序号，点开可以看到原网页地址、页面声明的发布时间、读取时间和逐字摘录。摘录必须能在原文中找到；来源之间有冲突会如实列出，不会取平均或隐藏。' },
  { q: '能导出哪些格式？',
    a: '回答和报告可以下载 Word、PDF、HTML 和 Markdown；采集的数据导出为 Excel（含字段字典、来源和分析图表），也提供 CSV 和 JSON。' },
  { q: '支持哪些大模型？怎么配置？',
    a: '支持 OpenAI、DeepSeek、Kimi、火山方舟、通义千问、智谱以及任意 OpenAI 兼容接口。管理员可以在「管理后台 → 大模型」或配置文件中添加，并为 8 个智能体分别指定模型和备用模型。' },
  { q: '数据存在哪里？能私有部署吗？',
    a: '对话、任务、来源与文件保存在服务方部署的数据库和存储中。可以部署在你自己的服务器上，支持 MySQL，数据不离开你的环境（调用大模型时会把必要内容发给你配置的模型服务）。' },
]
const openFaq = ref<number | null>(0)
</script>

<template>
  <div class="relative" style="background: var(--cs-bg)">
    <!-- 产品界面示意 + 认识云搜浏览器 -->
    <section id="intro" class="mx-auto max-w-[1200px] scroll-mt-16 px-5 pt-20 md:px-8" aria-labelledby="intro-title">
      <div v-reveal class="mx-auto max-w-[1080px]">
        <LandingMockup />
      </div>
      <div class="mx-auto mt-20 grid max-w-[1040px] gap-8 md:grid-cols-[minmax(0,360px)_1fr] md:gap-14">
        <div v-reveal>
          <span class="lp-eyebrow"><Sparkles class="h-3.5 w-3.5" /> 认识云搜浏览器</span>
          <h2 id="intro-title" class="lp-h2 mt-4 !text-[clamp(26px,3.2vw,36px)]">把查资料这件事，<br />交给云端完成</h2>
        </div>
        <div v-reveal="80" class="space-y-6 text-[17px] leading-8 md:text-lg md:leading-9">
          <p class="text-slate-400">
            <b class="font-semibold text-white">普通的 AI 回答，往往没法直接用。</b>
            没有出处，无从核对；不会真的去浏览网页，资料停留在训练时；遇到验证码就卡住；给出的是一段文字，还得自己整理成报告和表格。
          </p>
          <p class="text-slate-400">
            <b class="font-semibold text-white">你只管提问，过程由云端跑完。</b>
            说出需求后，云端浏览器和 8 个分工协作的智能体会去搜索、打开网页、抽取并核验信息，最后交付带引用的回答、可下载的报告和整理好的数据。
          </p>
        </div>
      </div>
    </section>

    <!-- 能力亮点 -->
    <section id="features" class="mx-auto mt-28 max-w-[1200px] scroll-mt-16 px-5 md:px-8" aria-labelledby="features-title">
      <div v-reveal class="mx-auto max-w-[760px] text-center">
        <span class="lp-eyebrow">能力亮点</span>
        <h2 id="features-title" class="lp-h2 mt-4">从一个问题，到可以直接交付的成果</h2>
        <p class="mt-4 text-[17px] leading-8 text-slate-400">搜索、阅读、核验、整理、排版，一次完成；每一步都看得见、查得到。</p>
      </div>
      <div class="mt-14">
        <LandingFeatures />
      </div>
    </section>

    <!-- 工作方式 -->
    <section id="how" class="mt-28 scroll-mt-16 py-24" style="background: var(--lp-section-alt)" aria-labelledby="how-title">
      <div class="mx-auto max-w-[1200px] px-5 md:px-8">
        <div v-reveal class="mx-auto max-w-[760px] text-center">
          <span class="lp-eyebrow">工作方式</span>
          <h2 id="how-title" class="lp-h2 mt-4">四步，从需求到成果</h2>
        </div>
        <ol class="relative mt-14 grid gap-6 md:grid-cols-4 md:gap-5">
          <div class="pointer-events-none absolute top-7 right-[12%] left-[12%] hidden h-px bg-gradient-to-r from-brand-400/0 via-brand-400/50 to-brand-400/0 md:block" aria-hidden="true" />
          <li v-for="(s, i) in STEPS" :key="s.title" v-reveal="i * 90" class="relative flex gap-4 md:flex-col md:items-center md:text-center">
            <span class="relative z-[1] flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border shadow-sm" style="background: var(--cs-surface-solid); border-color: var(--cs-line-strong)">
              <component :is="s.icon" class="h-6 w-6 text-brand-300" />
              <span class="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-brand-500 text-[11px] font-semibold text-snow">{{ i + 1 }}</span>
            </span>
            <div>
              <h3 class="text-[17px] font-semibold tracking-tight text-white md:mt-5">{{ s.title }}</h3>
              <p class="mt-1.5 text-sm leading-6 text-slate-400">{{ s.desc }}</p>
            </div>
          </li>
        </ol>
      </div>
    </section>

    <!-- 使用场景 -->
    <section id="scenarios" class="mx-auto mt-28 max-w-[1200px] scroll-mt-16 px-5 md:px-8" aria-labelledby="scenarios-title">
      <div v-reveal class="mx-auto max-w-[760px] text-center">
        <span class="lp-eyebrow">使用场景</span>
        <h2 id="scenarios-title" class="lp-h2 mt-4">需要查资料的地方，都能用上</h2>
      </div>
      <div v-reveal="80" class="mt-12 grid gap-6 lg:grid-cols-[300px_1fr]">
        <div role="tablist" aria-label="使用场景" aria-orientation="vertical" class="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible" @keydown="onTabKey">
          <button
            v-for="(s, i) in SCENARIOS"
            :key="s.key"
            :ref="(el) => { if (el) tabRefs[i] = el as HTMLButtonElement }"
            type="button"
            role="tab"
            :id="`tab-${s.key}`"
            :aria-selected="i === activeIdx"
            :aria-controls="`panel-${s.key}`"
            :tabindex="i === activeIdx ? 0 : -1"
            class="flex shrink-0 items-center gap-3 rounded-2xl border px-4 py-3 text-left text-[15px] transition"
            :class="i === activeIdx ? 'border-brand-400/50 bg-brand-500/10 font-medium text-white shadow-sm' : 'hairline text-slate-300 hover:bg-white/5'"
            @click="activeIdx = i"
          >
            <component :is="s.icon" class="h-[18px] w-[18px]" :class="i === activeIdx ? 'text-brand-300' : 'text-slate-400'" />
            {{ s.label }}
          </button>
        </div>
        <div
          :id="`panel-${active.key}`"
          role="tabpanel"
          :aria-labelledby="`tab-${active.key}`"
          class="flex flex-col justify-between gap-8 rounded-[24px] border p-7 md:p-10"
          style="background: var(--lp-tint-indigo); border-color: var(--cs-line)"
        >
          <div>
            <div class="flex items-center gap-3">
              <span class="flex h-11 w-11 items-center justify-center rounded-xl" style="background: var(--cs-surface-solid)">
                <component :is="active.icon" class="h-5 w-5 text-brand-300" />
              </span>
              <h3 class="text-2xl font-semibold tracking-tight text-white">{{ active.label }}</h3>
              <span class="rounded-full bg-white/6 px-2.5 py-0.5 text-xs text-slate-300">{{ active.modeLabel }}</span>
            </div>
            <p class="mt-4 text-[16px] leading-7 text-slate-300">{{ active.desc }}</p>
          </div>
          <div class="rounded-2xl border p-4 md:p-5" style="background: var(--cs-surface-solid); border-color: var(--cs-line)">
            <div class="text-xs text-slate-400">示例问题</div>
            <p class="mt-1.5 text-[15px] leading-7 text-white">“{{ active.prompt }}”</p>
            <button type="button" class="btn-primary mt-4" @click="emit('try', active.mode, active.prompt)">
              试试这个 <ArrowRight class="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- 安全可信（深色分栏） -->
    <section id="security" class="mx-auto mt-28 max-w-[1200px] scroll-mt-16 px-5 md:px-8" aria-labelledby="security-title">
      <div v-reveal class="lp-dark grid overflow-hidden rounded-[28px] md:grid-cols-2">
        <div class="p-8 md:p-14">
          <span class="inline-flex items-center gap-1.5 rounded-full border border-[#ffffff26] px-3 py-1 text-xs text-[#c7d2fe]">
            <ShieldCheck class="h-3.5 w-3.5" /> 安全可信
          </span>
          <h2 id="security-title" class="mt-5 text-3xl leading-tight font-semibold tracking-tight text-snow md:text-[38px]">
            经得起核对，<br /><span class="text-[#94a3b8]">才敢拿去用。</span>
          </h2>
          <ul class="mt-9 space-y-5">
            <li v-for="t in TRUST" :key="t.title">
              <div class="text-[15px] font-medium text-snow">{{ t.title }}</div>
              <div class="mt-1 text-sm leading-6 text-[#94a3b8]">{{ t.desc }}</div>
            </li>
          </ul>
        </div>
        <div class="lp-dark-visual flex items-center justify-center p-8 md:p-12" aria-hidden="true">
          <div class="w-full max-w-[400px] space-y-3">
            <div class="flex items-center justify-between rounded-2xl border border-[#ffffff1f] bg-[#ffffff0d] px-4 py-3">
              <span class="flex items-center gap-2 text-sm text-[#e2e8f0]"><Lock class="h-4 w-4 text-[#a5b4fc]" /> API Key</span>
              <span class="font-mono text-sm tracking-widest text-[#94a3b8]">sk-****f3a9</span>
            </div>
            <div class="rounded-2xl border border-[#ffffff1f] bg-[#ffffff0d] p-4">
              <div class="text-[13px] text-[#e2e8f0]">[1] 导览 - 故宫博物院 · dpm.org.cn</div>
              <div class="mt-2 rounded-lg bg-[#fcd34d24] px-2.5 py-1.5 text-[13px] text-[#fde68a]">“每周一闭馆（法定节假日除外）”</div>
              <div class="mt-3 space-y-1.5 text-[12.5px] text-[#a7f3d0]">
                <div>✓ 摘录与原文逐字一致</div>
                <div>✓ 发布时间取自页面声明</div>
                <div>✓ 读取时间 2026-11-13 10:02</div>
              </div>
            </div>
            <div class="flex items-center gap-2 rounded-2xl border border-[#ffffff1f] bg-[#ffffff0d] px-4 py-3 text-[13px] text-[#cbd5e1]">
              <span class="h-2 w-2 rounded-full bg-[#f59e0b]" /> 人工接管中 · 画面不保存 · AI 已暂停
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 支持的大模型 -->
    <section id="models" class="mx-auto mt-24 max-w-[1200px] scroll-mt-16 px-5 md:px-8" aria-labelledby="models-title">
      <div v-reveal class="text-center">
        <h2 id="models-title" class="text-sm font-medium tracking-wide text-slate-400">支持的大模型 · 可为每个智能体单独指定</h2>
        <div class="mt-5 flex flex-wrap justify-center gap-2.5">
          <span v-for="m in MODELS" :key="m" class="rounded-full border px-4 py-1.5 text-sm text-slate-200" style="background: var(--cs-surface-solid); border-color: var(--cs-line)">{{ m }}</span>
        </div>
      </div>
    </section>

    <!-- 常见问题 -->
    <section id="faq" class="mx-auto mt-28 max-w-[880px] scroll-mt-16 px-5 md:px-8" aria-labelledby="faq-title">
      <div v-reveal class="text-center">
        <span class="lp-eyebrow">常见问题</span>
        <h2 id="faq-title" class="lp-h2 mt-4">你可能想知道</h2>
      </div>
      <div v-reveal="80" class="mt-10 divide-y rounded-[22px] border" style="background: var(--cs-surface-solid); border-color: var(--cs-line); --tw-divide-opacity: 1">
        <div v-for="(f, i) in FAQ" :key="f.q" class="hairline">
          <h3>
            <button
              :id="`faq-q-${i}`"
              type="button"
              class="flex w-full items-center justify-between gap-4 px-6 py-5 text-left text-[16px] font-medium text-white"
              :aria-expanded="openFaq === i"
              :aria-controls="`faq-a-${i}`"
              @click="openFaq = openFaq === i ? null : i"
            >
              {{ f.q }}
              <ChevronDown class="h-5 w-5 shrink-0 text-slate-400 transition-transform" :class="openFaq === i ? 'rotate-180' : ''" />
            </button>
          </h3>
          <div v-show="openFaq === i" :id="`faq-a-${i}`" role="region" :aria-labelledby="`faq-q-${i}`" class="px-6 pb-5 text-[15px] leading-7 text-slate-400">
            {{ f.a }}
          </div>
        </div>
      </div>
    </section>

    <!-- 结尾行动号召 -->
    <section class="mx-auto mt-28 max-w-[1200px] px-5 md:px-8" aria-labelledby="cta-title">
      <div v-reveal class="lp-cta relative overflow-hidden rounded-[28px] px-6 py-20 text-center md:py-28">
        <h2 id="cta-title" class="lp-h2 relative">从一个问题开始</h2>
        <p class="relative mt-4 text-[17px] text-slate-300">说出你想知道的，剩下的交给云端去搜、去读、去整理。</p>
        <button type="button" class="btn-primary relative mt-8 px-6 py-3 text-base" @click="emit('start')">
          <Search class="h-4 w-4" /> 开始搜索
        </button>
      </div>
    </section>

    <!-- 页脚 -->
    <footer class="mx-auto mt-24 max-w-[1200px] px-5 pb-10 md:px-8">
      <div class="grid grid-cols-2 gap-8 md:grid-cols-4">
        <div>
          <div class="text-sm text-slate-500">产品</div>
          <ul class="mt-3 space-y-2.5 text-sm text-slate-200">
            <li><button type="button" class="hover:text-brand-300" @click="go('features')">功能亮点</button></li>
            <li><button type="button" class="hover:text-brand-300" @click="go('how')">工作方式</button></li>
            <li><button type="button" class="hover:text-brand-300" @click="go('security')">安全可信</button></li>
            <li><button type="button" class="hover:text-brand-300" @click="go('models')">支持的大模型</button></li>
          </ul>
        </div>
        <div>
          <div class="text-sm text-slate-500">场景</div>
          <ul class="mt-3 space-y-2.5 text-sm text-slate-200">
            <li v-for="(s, i) in SCENARIOS.slice(0, 4)" :key="s.key">
              <button type="button" class="hover:text-brand-300" @click="activeIdx = i; go('scenarios')">{{ s.label }}</button>
            </li>
          </ul>
        </div>
        <div>
          <div class="text-sm text-slate-500">资源</div>
          <ul class="mt-3 space-y-2.5 text-sm text-slate-200">
            <li><button type="button" class="hover:text-brand-300" @click="go('faq')">常见问题</button></li>
            <template v-if="loggedIn">
              <li><RouterLink to="/artifacts" class="hover:text-brand-300">我的成果</RouterLink></li>
              <li><RouterLink to="/settings" class="hover:text-brand-300">设置</RouterLink></li>
            </template>
          </ul>
        </div>
        <div>
          <div class="text-sm text-slate-500">开始使用</div>
          <ul class="mt-3 space-y-2.5 text-sm text-slate-200">
            <li><button type="button" class="hover:text-brand-300" @click="emit('start')">开始搜索</button></li>
            <template v-if="!loggedIn">
              <li><RouterLink :to="{ name: 'login', query: { redirect: '/' } }" class="hover:text-brand-300">登录</RouterLink></li>
              <li><RouterLink :to="{ name: 'login', query: { redirect: '/', tab: 'register' } }" class="hover:text-brand-300">注册账号</RouterLink></li>
            </template>
          </ul>
        </div>
      </div>
      <div class="hairline mt-14 border-t pt-6 text-sm text-slate-500">© 2026 云搜浏览器</div>
    </footer>
  </div>
</template>

<style scoped>
.lp-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--color-brand-400) 35%, transparent);
  background: color-mix(in srgb, var(--color-brand-500) 9%, transparent);
  padding: 4px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-brand-300);
}
.lp-h2 {
  text-wrap: balance;
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.18;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--color-white);
}
/* 深色分栏：两种主题下都保持深色，文字使用固定颜色（不随主题翻转） */
.lp-dark {
  background: #0d1326;
  border: 1px solid #ffffff14;
  box-shadow: 0 30px 60px -30px rgba(15, 23, 42, 0.55);
}
.lp-dark-visual {
  background:
    radial-gradient(420px 320px at 70% 30%, rgba(99, 102, 241, 0.35), transparent 70%),
    radial-gradient(360px 300px at 20% 90%, rgba(20, 184, 166, 0.22), transparent 70%),
    #0a1022;
}
.lp-cta {
  background:
    radial-gradient(60% 80% at 50% 110%, color-mix(in srgb, var(--color-brand-500) 45%, transparent), transparent 70%),
    radial-gradient(40% 60% at 15% 0%, color-mix(in srgb, #2dd4bf 22%, transparent), transparent 70%),
    var(--lp-tint-indigo);
  border: 1px solid var(--cs-line);
}
.lp-cta::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(color-mix(in srgb, var(--color-brand-400) 35%, transparent) 1px, transparent 1.2px);
  background-size: 18px 18px;
  mask-image: radial-gradient(70% 60% at 50% 100%, #000 30%, transparent 75%);
  -webkit-mask-image: radial-gradient(70% 60% at 50% 100%, #000 30%, transparent 75%);
  pointer-events: none;
}
</style>
