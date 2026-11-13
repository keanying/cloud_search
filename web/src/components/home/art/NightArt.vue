<script setup lang="ts">
// 「星夜」：深靛蓝夜空、星星、弯月与远山（原创矢量插画，配合深色模式）
// 用固定种子生成星星位置，保证每次渲染一致
let seed = 7
const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280)
const stars = Array.from({ length: 90 }, () => ({
  x: Math.round(rnd() * 1600),
  y: Math.round(rnd() * 560),
  r: +(0.6 + rnd() * 1.6).toFixed(2),
  d: +(rnd() * 4).toFixed(2),
}))
</script>

<template>
  <svg class="h-full w-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs>
      <linearGradient id="night-sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#070b1f" />
        <stop offset="0.6" stop-color="#151a45" />
        <stop offset="1" stop-color="#2b2670" />
      </linearGradient>
      <mask id="night-moon">
        <rect width="1600" height="900" fill="#fff" />
        <circle cx="1318" cy="176" r="56" fill="#000" />
      </mask>
      <radialGradient id="night-glow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stop-color="#c7d2fe" stop-opacity="0.35" />
        <stop offset="1" stop-color="#c7d2fe" stop-opacity="0" />
      </radialGradient>
    </defs>
    <rect width="1600" height="900" fill="url(#night-sky)" />
    <circle cx="1290" cy="200" r="150" fill="url(#night-glow)" />
    <circle cx="1290" cy="200" r="62" fill="#fef3c7" mask="url(#night-moon)" />
    <g fill="#ffffff">
      <circle
        v-for="(s, i) in stars"
        :key="i"
        class="star"
        :cx="s.x"
        :cy="s.y"
        :r="s.r"
        :style="{ animationDelay: `${-s.d}s` }"
      />
    </g>
    <path class="meteor" d="M300 120 l-90 42" stroke="#e0e7ff" stroke-width="2" stroke-linecap="round" opacity="0" />
    <path d="M0 700 L180 610 L320 680 L520 580 L700 670 L880 600 L1060 690 L1260 600 L1440 670 L1600 620 V900 H0 Z" fill="#1e1b4b" />
    <path d="M0 780 L220 710 L420 770 L640 700 L860 780 L1080 720 L1300 790 L1600 730 V900 H0 Z" fill="#17153b" />
    <path d="M0 850 C 400 820 800 860 1200 840 S 1500 830 1600 840 V900 H0 Z" fill="#0f0d2b" />
  </svg>
</template>

<style scoped>
.star {
  animation: twinkle 4s ease-in-out infinite;
}
.meteor {
  animation: meteor 11s ease-in infinite;
}
@keyframes twinkle {
  50% {
    opacity: 0.35;
  }
}
@keyframes meteor {
  0%,
  88% {
    opacity: 0;
    transform: translate(0, 0);
  }
  92% {
    opacity: 0.9;
  }
  100% {
    opacity: 0;
    transform: translate(-160px, 76px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .star,
  .meteor {
    animation: none;
  }
}
</style>
