<script setup lang="ts">
// 「荷塘」：青绿色水面、荷叶、荷花与两尾小鱼（原创矢量插画）
const pads = [
  { x: 180, y: 720, r: 52 }, { x: 330, y: 800, r: 40 }, { x: 560, y: 760, r: 34 },
  { x: 1080, y: 740, r: 46 }, { x: 1300, y: 820, r: 58 }, { x: 1460, y: 700, r: 36 }, { x: 820, y: 850, r: 30 },
]
</script>

<template>
  <svg class="h-full w-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs>
      <linearGradient id="pond-sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#effcf8" />
        <stop offset="1" stop-color="#f3fbff" />
      </linearGradient>
      <linearGradient id="pond-water" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#a7f3e4" />
        <stop offset="0.45" stop-color="#5eead4" />
        <stop offset="1" stop-color="#0f9488" />
      </linearGradient>
    </defs>
    <rect width="1600" height="900" fill="url(#pond-sky)" />
    <path d="M0 600 C 300 585 600 610 900 598 S 1400 588 1600 600 V900 H0 Z" fill="url(#pond-water)" />
    <g fill="none" stroke="#ffffff" stroke-opacity="0.5" stroke-width="2">
      <ellipse class="ripple" cx="430" cy="690" rx="60" ry="10" />
      <ellipse class="ripple r2" cx="1180" cy="660" rx="80" ry="12" />
      <ellipse cx="900" cy="760" rx="50" ry="8" />
    </g>
    <g v-for="(p, i) in pads" :key="i" :transform="`translate(${p.x} ${p.y})`">
      <ellipse :rx="p.r" :ry="p.r * 0.42" fill="#10b981" />
      <ellipse :rx="p.r * 0.86" :ry="p.r * 0.34" fill="#34d399" />
      <path :d="`M0 0 L${p.r} ${-p.r * 0.12} L${p.r} ${p.r * 0.12} Z`" fill="#2dd4bf" />
    </g>
    <g transform="translate(1300 790)">
      <ellipse cx="-14" cy="-14" rx="12" ry="26" fill="#f9a8d4" transform="rotate(-28)" />
      <ellipse cx="14" cy="-14" rx="12" ry="26" fill="#f9a8d4" transform="rotate(28)" />
      <ellipse cx="0" cy="-22" rx="12" ry="28" fill="#f472b6" />
      <circle cx="0" cy="-6" r="7" fill="#fde68a" />
    </g>
    <g class="fish">
      <g transform="translate(700 700)">
        <ellipse rx="34" ry="13" fill="#fb923c" />
        <path d="M30 0 L56 -14 L52 0 L56 14 Z" fill="#f97316" />
        <circle cx="-20" cy="-3" r="2.5" fill="#7c2d12" />
      </g>
    </g>
    <g class="fish f2">
      <g transform="translate(980 810) scale(-0.8 0.8)">
        <ellipse rx="34" ry="13" fill="#fbbf24" />
        <path d="M30 0 L56 -14 L52 0 L56 14 Z" fill="#f59e0b" />
        <circle cx="-20" cy="-3" r="2.5" fill="#78350f" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.fish {
  animation: swim 14s ease-in-out infinite alternate;
}
.f2 {
  animation-duration: 18s;
  animation-direction: alternate-reverse;
}
.ripple {
  transform-box: fill-box;
  transform-origin: center;
  animation: ripple 6s ease-in-out infinite;
}
.r2 {
  animation-delay: -3s;
}
@keyframes swim {
  to {
    transform: translateX(-120px) translateY(10px);
  }
}
@keyframes ripple {
  50% {
    transform: scale(1.25);
    opacity: 0.3;
  }
}
@media (prefers-reduced-motion: reduce) {
  .fish,
  .ripple {
    animation: none;
  }
}
</style>
