<!-- 首页主题「幻彩」：柔和的幻彩光斑 + 两张悬浮的磨砂玻璃卡片（纯装饰），与整体玻璃风格一致 -->
<template>
  <div class="absolute inset-0">
    <div class="blob left-[-8%] top-[-12%] h-[520px] w-[620px] bg-[#a78bfa]" />
    <div class="blob right-[-10%] top-[6%] h-[480px] w-[560px] bg-[#7dd3fc] [animation-delay:-6s]" />
    <div class="blob bottom-[-18%] left-[18%] h-[460px] w-[620px] bg-[#f9a8d4] [animation-delay:-11s]" />
    <div class="blob bottom-[-10%] right-[8%] h-[380px] w-[460px] bg-[#86efac] opacity-40 [animation-delay:-3s]" />

    <!-- 悬浮玻璃卡片（宽屏显示） -->
    <div class="float-card holo-card left-[7%] top-[24%] hidden -rotate-[10deg] xl:block">
      <span class="chip-mark" />
      <span class="bar w-24" />
      <span class="bar mt-2 w-16 opacity-70" />
    </div>
    <div class="float-card glass-card right-[8%] top-[58%] hidden rotate-[8deg] xl:block [animation-delay:-4s]">
      <span class="dot-row"><i /><i /><i /></span>
      <span class="bar mt-5 w-28" />
      <span class="bar mt-2 w-20 opacity-70" />
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
:global(html.dark) .blob {
  opacity: 0.22;
}
@keyframes drift {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(40px, 30px, 0) scale(1.08); }
}
.float-card {
  position: absolute;
  width: 230px;
  height: 140px;
  border-radius: 26px;
  padding: 20px 22px;
  border: 1px solid rgba(255, 255, 255, 0.75);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7), 0 30px 60px -28px rgba(40, 44, 90, 0.45);
  backdrop-filter: blur(18px) saturate(1.6);
  animation: bob 9s ease-in-out infinite;
}
.holo-card {
  background: linear-gradient(125deg, rgba(255, 200, 236, 0.75), rgba(201, 188, 255, 0.75) 35%, rgba(168, 228, 255, 0.75) 68%, rgba(196, 245, 223, 0.75));
}
.glass-card {
  background: linear-gradient(135deg, rgba(112, 114, 255, 0.85), rgba(123, 92, 255, 0.75) 55%, rgba(125, 211, 252, 0.7));
}
:global(html.dark) .float-card {
  border-color: rgba(255, 255, 255, 0.12);
  opacity: 0.75;
}
@keyframes bob {
  0%, 100% { translate: 0 0; }
  50% { translate: 0 -12px; }
}
.chip-mark {
  display: block;
  width: 34px;
  height: 26px;
  border-radius: 7px;
  margin-bottom: 26px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(220, 222, 240, 0.9));
  box-shadow: inset 0 0 0 1px rgba(30, 35, 80, 0.12);
}
.bar {
  display: block;
  height: 8px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.85);
}
.dot-row {
  display: flex;
  justify-content: flex-end;
}
.dot-row i {
  width: 22px;
  height: 22px;
  border-radius: 9999px;
  margin-left: -8px;
}
.dot-row i:nth-child(1) { background: #f0577a; }
.dot-row i:nth-child(2) { background: #f5a524; opacity: 0.9; }
.dot-row i:nth-child(3) { background: rgba(255, 255, 255, 0.85); }
@media (prefers-reduced-motion: reduce) {
  .blob, .float-card { animation: none; }
}
</style>
