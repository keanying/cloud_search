<script setup lang="ts">
import { vReveal } from '@/lib/reveal'

const AGENTS = ['需求编译', '协调', '搜索规划', '浏览研究', '信息抽取', '核验', '分析', '报告写作']
const SOURCES = ['DuckDuckGo', 'Google', '必应', '百度', '搜狗', '维基百科', '百度百科', '微信公众号', 'GitHub', 'arXiv', '自定义来源']
const BARS = [62, 88, 45, 74, 56]
</script>

<template>
  <div class="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
    <!-- ① 多智能体分工 -->
    <article v-reveal class="lp-card">
      <div class="lp-visual" style="background: var(--lp-tint-indigo)">
        <div class="lp-bubble">帮我研究新能源汽车出海的主要市场</div>
        <div class="mt-3 flex flex-wrap gap-1.5">
          <span
            v-for="(a, i) in AGENTS"
            :key="a"
            class="rounded-full border px-2 py-0.5 text-[11px]"
            :class="i < 4 ? 'border-brand-400/40 bg-brand-500/12 text-brand-300' : 'hairline text-slate-400'"
          >{{ a }}</span>
        </div>
      </div>
      <h3 class="lp-card-title">一句话发起，多智能体分工</h3>
      <p class="lp-card-desc">描述需求即可。8 个智能体各司其职：理解需求、规划搜索、浏览读取、抽取信息、核验、分析和写作，调度与预算由程序控制。</p>
    </article>

    <!-- ② 云端浏览器全程可见 -->
    <article v-reveal="80" class="lp-card">
      <div class="lp-visual" style="background: var(--lp-tint-teal)">
        <div class="hairline overflow-hidden rounded-xl border" style="background: var(--lp-mock-bg)">
          <div class="hairline flex items-center gap-2 border-b px-2.5 py-1.5 text-[10.5px] text-slate-400">
            <span class="truncate rounded bg-white/5 px-1.5">duckduckgo.com/?q=…</span>
            <span class="ml-auto flex items-center gap-1 rounded-full bg-emerald-500/12 px-1.5 text-emerald-300">
              <span class="lp-pulse h-1.5 w-1.5 rounded-full bg-emerald-400" />实时
            </span>
          </div>
          <div class="space-y-1.5 p-2.5">
            <div v-for="i in 3" :key="i" class="space-y-1">
              <div class="h-2 w-2/3 rounded bg-brand-500/30" />
              <div class="h-1.5 w-11/12 rounded bg-white/8" />
            </div>
          </div>
        </div>
      </div>
      <h3 class="lp-card-title">云端浏览器全程可见</h3>
      <p class="lp-card-desc">搜索和读取都在云端真实浏览器中进行，右侧面板实时显示画面。关闭面板不影响任务，随时可以回来看。</p>
    </article>

    <!-- ③ 每一句都有出处 -->
    <article v-reveal="160" class="lp-card">
      <div class="lp-visual" style="background: var(--lp-tint-amber)">
        <p class="text-[12.5px] leading-6 text-slate-200">故宫博物院每周一闭馆，法定节假日除外<span class="cite-chip">1</span>，旺季实行实名预约<span class="cite-chip">2</span>。</p>
        <div class="hairline mt-2.5 rounded-xl border p-2.5 text-[11px]" style="background: var(--lp-mock-bg)">
          <div class="font-medium text-white">[1] 导览 - 故宫博物院</div>
          <div class="mt-0.5 text-slate-400">dpm.org.cn · 发布 2026-02-10 · 读取 11-13 10:02</div>
          <div class="mt-1.5 rounded-md bg-amber-300/25 px-1.5 py-0.5 text-amber-200">“每周一闭馆（法定节假日除外）”</div>
        </div>
      </div>
      <h3 class="lp-card-title">每一句都有出处</h3>
      <p class="lp-card-desc">事实句标注来源序号，点击即可查看原网页、发布时间、读取时间和逐字摘录。摘录对不上原文的内容会被丢弃。</p>
    </article>

    <!-- ④ 报告与数据直接可用 -->
    <article v-reveal class="lp-card">
      <div class="lp-visual" style="background: var(--lp-tint-sky)">
        <div class="flex h-24 items-end gap-2.5 px-1" aria-hidden="true">
          <div v-for="(h, i) in BARS" :key="i" class="flex-1 rounded-t-xl" :style="{ height: h + '%', background: ['var(--pastel-sky-dot)', 'var(--pastel-lilac-dot)', 'var(--pastel-mint-dot)', 'var(--pastel-butter-dot)', 'var(--pastel-peach-dot)'][i % 5] }" />
        </div>
        <div class="mt-3 flex gap-1.5">
          <span class="rounded-md bg-brand-500/12 px-2 py-0.5 text-[11px] text-brand-300">Word</span>
          <span class="rounded-md bg-rose-500/12 px-2 py-0.5 text-[11px] text-rose-300">PDF</span>
          <span class="rounded-md bg-emerald-500/12 px-2 py-0.5 text-[11px] text-emerald-300">Excel</span>
          <span class="rounded-md bg-white/6 px-2 py-0.5 text-[11px] text-slate-300">HTML</span>
        </div>
      </div>
      <h3 class="lp-card-title">报告与数据直接可用</h3>
      <p class="lp-card-desc">自动排版成摘要、要点、对比表格和图表，可下载 Word、PDF、HTML；采集的数据整理为带字段说明和来源的 Excel。图表数字都能在来源中找到。</p>
    </article>

    <!-- ⑤ 人工接管 -->
    <article v-reveal="80" class="lp-card">
      <div class="lp-visual" style="background: var(--lp-tint-pink)">
        <div class="rounded-xl border border-amber-400/40 bg-amber-300/15 p-3">
          <div class="text-[12.5px] font-semibold text-white">需要你协助：搜索引擎要求人机验证</div>
          <div class="mt-1 text-[11px] text-slate-400">AI 已暂停在该页面 · 4:56 后自动跳过</div>
          <div class="mt-2.5 flex gap-2">
            <span class="rounded-full bg-[var(--cs-ink)] px-2.5 py-1 text-[11px] font-semibold text-[var(--cs-on-ink)]">接手处理</span>
            <span class="rounded-lg bg-white/6 px-2.5 py-1 text-[11px] text-slate-300">跳过</span>
          </div>
        </div>
      </div>
      <h3 class="lp-card-title">遇到人机验证，人来接手</h3>
      <p class="lp-card-desc">碰到验证码或登录页，AI 会暂停并请你在实时画面里直接操作，完成后交还 AI 继续；无人处理会按时跳过，不会绕过验证。</p>
    </article>

    <!-- ⑥ 多个搜索来源 -->
    <article v-reveal="160" class="lp-card">
      <div class="lp-visual" style="background: var(--lp-tint-violet)">
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="(s, i) in SOURCES"
            :key="s"
            class="rounded-lg border px-2 py-1 text-[11px]"
            :class="i === 0 ? 'border-brand-400/50 bg-brand-500/12 text-brand-300' : 'hairline text-slate-300'"
            style="background-color: var(--lp-mock-bg)"
          >{{ s }}</span>
        </div>
      </div>
      <h3 class="lp-card-title">不止一个搜索引擎</h3>
      <p class="lp-card-desc">按意图改写搜索词，在多个引擎间自动切换；百科、公众号文章、论文、代码等用对应网站的站内搜索，也可以自己添加来源。</p>
    </article>
  </div>
</template>

<style scoped>
.lp-card {
  border: 1px solid var(--cs-line);
  border-radius: 30px;
  padding: 12px 12px 22px;
  background: var(--cs-surface-solid);
  box-shadow: var(--cs-shadow);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.lp-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--cs-shadow-lg);
}
.lp-visual {
  border-radius: 22px;
  padding: 18px;
  min-height: 176px;
}
.lp-bubble {
  width: fit-content;
  margin-left: auto;
  border-radius: 14px 14px 4px 14px;
  background: var(--cs-ink);
  color: var(--cs-on-ink);
  padding: 6px 12px;
  font-size: 12px;
}
.lp-card-title {
  margin: 18px 10px 6px;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--color-white);
}
.lp-card-desc {
  margin: 0 10px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-slate-400);
}
@media (prefers-reduced-motion: reduce) {
  .lp-card:hover { transform: none; }
}
</style>
