<!-- 首页主题「幻彩」：柔和的幻彩光斑 + 几个悬浮的磨砂玻璃小部件（读网页、核验来源、生成图表，纯装饰） -->
<template>
  <div class="absolute inset-0">
    <div class="blob left-[-8%] top-[-12%] h-[520px] w-[620px] bg-[#a78bfa]" />
    <div class="blob right-[-10%] top-[6%] h-[480px] w-[560px] bg-[#7dd3fc] [animation-delay:-6s]" />
    <div class="blob bottom-[-18%] left-[18%] h-[460px] w-[620px] bg-[#f9a8d4] [animation-delay:-11s]" />
    <div class="blob bottom-[-10%] right-[8%] h-[380px] w-[460px] bg-[#86efac] opacity-40 [animation-delay:-3s]" />

    <!-- 悬浮玻璃小部件（宽屏显示）：读网页 → 核验来源 → 生成图表，呼应产品流程 -->
    <!-- 左：正在阅读的网页（高亮的句子即抽取的证据） -->
    <div class="widget left-[6%] top-[22%] hidden w-[250px] -rotate-[6deg] xl:block">
      <div class="flex items-center gap-1.5">
        <i class="h-2 w-2 rounded-full bg-[#f0577a]" /><i class="h-2 w-2 rounded-full bg-[#f5a524]" /><i class="h-2 w-2 rounded-full bg-[#22b07d]" />
        <span class="url ml-2 flex-1" />
      </div>
      <span class="line mt-4 w-3/4 !h-2.5 !bg-[rgba(30,35,80,.55)] dark:!bg-white/40" />
      <span class="line mt-3 w-full" />
      <span class="hl mt-2"><span class="line w-[86%] !bg-transparent" /></span>
      <span class="line mt-2 w-[92%]" />
      <span class="line mt-2 w-2/3" />
      <span class="tag mt-3">“引用 [1]”</span>
    </div>

    <!-- 右上：核验结果胶囊 -->
    <div class="pill-w right-[10%] top-[20%] hidden rotate-[4deg] xl:flex [animation-delay:-5s]">
      <span class="check">✓</span>
      <span>6 个来源已核验</span>
    </div>

    <!-- 右下：生成的图表 -->
    <div class="widget right-[7%] top-[52%] hidden w-[240px] rotate-[5deg] xl:block [animation-delay:-3s]">
      <div class="flex items-center justify-between">
        <span class="line !h-2.5 w-24 !bg-[rgba(30,35,80,.55)] dark:!bg-white/40" />
        <span class="badge">+38%</span>
      </div>
      <svg class="mt-3 w-full" viewBox="0 0 200 96" aria-hidden="true">
        <defs>
          <linearGradient id="ga-bar" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#6d6fff" /><stop offset="1" stop-color="#a5b4fc" stop-opacity=".55" />
          </linearGradient>
          <linearGradient id="ga-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#5b5cf6" stop-opacity=".22" /><stop offset="1" stop-color="#5b5cf6" stop-opacity="0" />
          </linearGradient>
        </defs>
        <g fill="url(#ga-bar)">
          <rect x="8" y="58" width="16" height="34" rx="5" /><rect x="40" y="40" width="16" height="52" rx="5" />
          <rect x="72" y="66" width="16" height="26" rx="5" /><rect x="104" y="30" width="16" height="62" rx="5" />
          <rect x="136" y="48" width="16" height="44" rx="5" /><rect x="168" y="16" width="16" height="76" rx="5" />
        </g>
        <path d="M16 62 C 32 50, 40 44, 48 46 S 72 62, 80 58 S 104 34, 112 36 S 136 46, 144 42 S 168 18, 176 14 L176 92 L16 92 Z" fill="url(#ga-area)" />
        <path d="M16 62 C 32 50, 40 44, 48 46 S 72 62, 80 58 S 104 34, 112 36 S 136 46, 144 42 S 168 18, 176 14" fill="none" stroke="#5b5cf6" stroke-width="2.5" stroke-linecap="round" />
        <g fill="#fff" stroke="#5b5cf6" stroke-width="2.2">
          <circle cx="48" cy="46" r="3.6" /><circle cx="112" cy="36" r="3.6" /><circle cx="176" cy="14" r="3.6" />
        </g>
      </svg>
    </div>

    <!-- 左下：搜索中胶囊 -->
    <div class="pill-w bottom-[24%] left-[12%] hidden -rotate-[3deg] xl:flex [animation-delay:-7s]">
      <span class="spin" />
      <span>正在阅读第 5 / 12 个网页</span>
    </div>
  </div>
</template>

<style scoped>
.blob {
  position: absolute;
  border-radius: 9999px;
  filter: blur(90px);
  opacity: 0.38;
  animation: drift 22s ease-in-out infinite alternate;
}
html.dark .blob {
  opacity: 0.22;
}
@keyframes drift {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(40px, 30px, 0) scale(1.08); }
}
.widget,
.pill-w {
  position: absolute;
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.55);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8), 0 26px 54px -26px rgba(40, 44, 90, 0.42);
  backdrop-filter: blur(18px) saturate(1.6);
  -webkit-backdrop-filter: blur(18px) saturate(1.6);
  animation: bob 9s ease-in-out infinite;
}
.widget {
  border-radius: 22px;
  padding: 16px 18px 18px;
}
.pill-w {
  align-items: center;
  gap: 0.5rem;
  border-radius: 999px;
  padding: 0.5rem 0.95rem 0.5rem 0.55rem;
  font-size: 12.5px;
  font-weight: 600;
  color: #33364d;
  white-space: nowrap;
}
html.dark .widget,
html.dark .pill-w {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(30, 32, 52, 0.55);
  color: #d2d5e6;
  opacity: 0.85;
}
@keyframes bob {
  0%, 100% { translate: 0 0; }
  50% { translate: 0 -12px; }
}
.url {
  height: 14px;
  border-radius: 999px;
  background: rgba(30, 35, 80, 0.07);
}
.line {
  display: block;
  height: 7px;
  border-radius: 999px;
  background: rgba(30, 35, 80, 0.13);
}
html.dark .line,
html.dark .url {
  background: rgba(255, 255, 255, 0.12);
}
.hl {
  display: block;
  padding: 3px 0;
  border-radius: 6px;
  background: linear-gradient(90deg, rgba(167, 139, 250, 0.45), rgba(125, 211, 252, 0.4));
}
.tag {
  display: inline-block;
  border-radius: 999px;
  padding: 2px 9px;
  font-size: 11px;
  font-weight: 700;
  color: #4f46e5;
  background: rgba(99, 102, 241, 0.12);
}
.badge {
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 700;
  color: #13704b;
  background: rgba(34, 176, 125, 0.16);
}
.check {
  display: inline-flex;
  height: 22px;
  width: 22px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 12px;
  color: #fff;
  background: linear-gradient(135deg, #34d399, #22b07d);
  box-shadow: 0 4px 10px -4px rgba(34, 176, 125, 0.7);
}
.spin {
  height: 20px;
  width: 20px;
  margin: 1px;
  border-radius: 999px;
  border: 2.5px solid rgba(91, 92, 246, 0.2);
  border-top-color: #5b5cf6;
  animation: spin 1.1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .blob, .widget, .pill-w, .spin { animation: none; }
}
</style>
