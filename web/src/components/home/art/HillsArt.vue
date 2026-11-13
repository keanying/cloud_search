<script setup lang="ts">
// 「山野」：层叠的平面山丘、简笔树与柔和的太阳（原创矢量插画）
const trees = [
  { x: 260, y: 640, s: 1 }, { x: 300, y: 652, s: 0.8 }, { x: 1180, y: 612, s: 1.1 },
  { x: 1228, y: 628, s: 0.85 }, { x: 1270, y: 640, s: 0.7 }, { x: 760, y: 700, s: 0.9 },
]
</script>

<template>
  <svg class="h-full w-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs>
      <linearGradient id="hills-sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#edf4ec" />
        <stop offset="0.6" stop-color="#f5f6ee" />
        <stop offset="1" stop-color="#faf7ee" />
      </linearGradient>
      <radialGradient id="hills-sun" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stop-color="#fde68a" />
        <stop offset="0.55" stop-color="#fcd34d" stop-opacity="0.9" />
        <stop offset="1" stop-color="#fcd34d" stop-opacity="0" />
      </radialGradient>
    </defs>
    <rect width="1600" height="900" fill="url(#hills-sky)" />
    <circle class="sun" cx="1290" cy="250" r="150" fill="url(#hills-sun)" opacity="0.55" />
    <circle cx="1290" cy="250" r="54" fill="#fde68a" opacity="0.9" />
    <g class="clouds" fill="#ffffff" opacity="0.8">
      <ellipse cx="300" cy="190" rx="90" ry="22" />
      <ellipse cx="350" cy="176" rx="60" ry="20" />
      <ellipse cx="1040" cy="150" rx="70" ry="16" />
    </g>
    <g fill="none" stroke="#2f6b4f" stroke-width="3" stroke-linecap="round" opacity="0.45">
      <path d="M520 230 q10 -10 20 0 q10 -10 20 0" />
      <path d="M570 260 q8 -8 16 0 q8 -8 16 0" />
    </g>
    <path d="M0 600 C 200 520 380 540 560 590 S 900 520 1100 560 S 1420 520 1600 570 V900 H0 Z" fill="#dbeadb" />
    <path d="M0 660 C 180 600 360 620 520 660 S 820 610 1000 640 S 1360 600 1600 640 V900 H0 Z" fill="#c3dfc6" />
    <path d="M0 720 C 220 660 420 700 640 720 S 980 670 1200 700 S 1480 690 1600 700 V900 H0 Z" fill="#a6d0b0" />
    <g v-for="(t, i) in trees" :key="i" :transform="`translate(${t.x} ${t.y}) scale(${t.s})`">
      <rect x="-3" y="18" width="6" height="22" fill="#2f5e46" opacity="0.7" />
      <path d="M0 -36 L22 22 H-22 Z" fill="#3a7d5a" opacity="0.85" />
    </g>
    <path d="M0 790 C 260 740 520 780 760 790 S 1180 750 1600 780 V900 H0 Z" fill="#86bf98" />
    <path d="M0 850 C 300 820 640 850 900 846 S 1360 820 1600 840 V900 H0 Z" fill="#5fa577" opacity="0.9" />
  </svg>
</template>

<style scoped>
.sun {
  transform-origin: 1290px 250px;
  animation: glow 8s ease-in-out infinite;
}
.clouds {
  animation: drift 40s linear infinite alternate;
}
@keyframes glow {
  50% {
    opacity: 0.75;
  }
}
@keyframes drift {
  to {
    transform: translateX(60px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sun,
  .clouds {
    animation: none;
  }
}
</style>
