<script setup lang="ts">
// 产品界面示意（纯 HTML/CSS 绘制，不含真实数据与外部图片）
</script>

<template>
  <div
    class="overflow-hidden rounded-[22px] border shadow-2xl"
    style="background: var(--lp-mock-bg); border-color: var(--cs-line-strong); box-shadow: var(--cs-shadow-lg)"
    role="img"
    aria-label="产品界面示意：左侧为对话与任务进度，右侧为实时的云端浏览器画面"
  >
    <!-- 窗口标题栏 -->
    <div class="hairline flex items-center gap-2 border-b px-4 py-2.5" style="background: var(--lp-mock-sub)">
      <span class="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
      <span class="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
      <span class="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
      <span class="ml-3 text-xs text-slate-400">云搜浏览器 · 博物馆开放政策</span>
    </div>
    <div class="grid md:grid-cols-[1.05fr_1fr]">
      <!-- 左：对话 -->
      <div class="space-y-3 p-4 md:p-5">
        <div class="ml-auto w-fit max-w-[85%] rounded-2xl rounded-tr-md bg-brand-500 px-3.5 py-2 text-[13px] text-snow">
          今年国内主要博物馆的开放时间和预约规则有什么变化？
        </div>
        <div class="hairline rounded-xl border p-3" style="background: var(--cs-surface-solid)">
          <div class="flex items-center justify-between text-[12px]">
            <span class="font-semibold text-white">搜索计划</span>
            <span class="rounded-full bg-emerald-500/12 px-2 py-0.5 text-[10px] text-emerald-300">已自动开始</span>
          </div>
          <div class="mt-2 flex flex-wrap gap-1.5 text-[10.5px] text-slate-300">
            <span class="rounded-md bg-white/5 px-1.5 py-0.5">site:dpm.org.cn 开放时间 公告</span>
            <span class="rounded-md bg-white/5 px-1.5 py-0.5">"国家博物馆" 预约 2026</span>
            <span class="rounded-md bg-white/5 px-1.5 py-0.5">博物馆 周一闭馆 新规</span>
          </div>
        </div>
        <div class="hairline rounded-xl border p-3 text-[12px]" style="background: var(--cs-surface-solid)">
          <div class="space-y-1.5 text-slate-300">
            <div class="flex items-center gap-2"><span class="text-emerald-300">✓</span> 规划搜索 · 理解意图</div>
            <div class="flex items-center gap-2"><span class="text-emerald-300">✓</span> 浏览器搜索 · DuckDuckGo</div>
            <div class="flex items-center gap-2"><span class="text-emerald-300">✓</span> 读取网页 · 6 个来源</div>
            <div class="flex items-center gap-2 text-white">
              <span class="lp-pulse inline-block h-2 w-2 rounded-full bg-brand-400" /> 核验原文摘录…
            </div>
          </div>
        </div>
        <div class="hairline rounded-xl border p-3 text-[12.5px] leading-6 text-slate-200" style="background: var(--cs-surface-solid)">
          <p>
            多数国家级博物馆保持<b class="text-white">周一闭馆、实名预约</b>
            <span class="cite-chip">1</span>；节假日实行预约限流，建议提前 7 天预约
            <span class="cite-chip">2</span>。
          </p>
          <div class="mt-2 flex gap-1.5">
            <span class="rounded-md bg-brand-500/12 px-2 py-0.5 text-[10.5px] text-brand-300">Word</span>
            <span class="rounded-md bg-rose-500/12 px-2 py-0.5 text-[10.5px] text-rose-300">PDF</span>
            <span class="rounded-md bg-emerald-500/12 px-2 py-0.5 text-[10.5px] text-emerald-300">Excel</span>
          </div>
        </div>
      </div>
      <!-- 右：云端浏览器 -->
      <div class="hairline hidden border-l p-4 md:block md:p-5" style="background: var(--lp-mock-sub)">
        <div class="flex items-center justify-between text-[12px]">
          <span class="font-semibold text-white">云端浏览器</span>
          <span class="flex items-center gap-1 rounded-full bg-emerald-500/12 px-2 py-0.5 text-[10px] text-emerald-300">
            <span class="lp-pulse h-1.5 w-1.5 rounded-full bg-emerald-400" /> 实时
          </span>
        </div>
        <div class="hairline mt-3 overflow-hidden rounded-xl border" style="background: var(--cs-surface-solid)">
          <div class="hairline flex items-center gap-2 border-b px-3 py-1.5 text-[10.5px] text-slate-400">
            <span class="h-2 w-2 rounded-full bg-white/10" />
            <span class="truncate rounded-md bg-white/5 px-2 py-0.5">https://www.dpm.org.cn/Visit.html</span>
          </div>
          <div class="space-y-2.5 p-3">
            <div class="h-16 rounded-lg bg-gradient-to-r from-[#b45309]/70 to-[#9f1239]/70" />
            <div class="grid grid-cols-3 gap-2">
              <div v-for="i in 3" :key="i" class="h-10 rounded-md bg-white/6" />
            </div>
            <div class="h-2 w-11/12 rounded bg-white/8" />
            <div class="h-2 w-9/12 rounded bg-white/8" />
            <div class="rounded-md bg-amber-300/25 px-2 py-1 text-[10.5px] text-amber-200">“每周一闭馆（法定节假日除外）……”</div>
            <div class="h-2 w-10/12 rounded bg-white/8" />
            <div class="h-2 w-7/12 rounded bg-white/8" />
          </div>
        </div>
        <div class="mt-3 text-[10.5px] text-slate-500">正在读取：故宫博物院 · 导览 · 已定位原文摘录</div>
      </div>
    </div>
  </div>
</template>
