<script setup lang="ts">
import { useId } from 'vue'

defineProps<{ size?: number }>()
const id = useId()
</script>

<template>
  <svg :width="size ?? 32" :height="size ?? 32" viewBox="0 0 64 64" aria-hidden="true">
    <defs>
      <linearGradient :id="`${id}-holo`" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#ffc8ec" />
        <stop offset="0.35" stop-color="#c9bcff" />
        <stop offset="0.68" stop-color="#a8e4ff" />
        <stop offset="1" stop-color="#c4f5df" />
      </linearGradient>
      <linearGradient :id="`${id}-ink`" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#6d6fff" />
        <stop offset="1" stop-color="#7b4dff" />
      </linearGradient>
    </defs>
    <rect x="4" y="4" width="56" height="56" rx="18" :fill="`url(#${id}-holo)`" />
    <rect x="4.5" y="4.5" width="55" height="55" rx="17.5" fill="none" stroke="#ffffff" stroke-opacity="0.8" />
    <circle cx="29" cy="29" r="12" fill="#fff" :stroke="`url(#${id}-ink)`" stroke-width="5" />
    <path d="M38 38 L47 47" :stroke="`url(#${id}-ink)`" stroke-width="5.5" stroke-linecap="round" />
    <circle cx="47" cy="17" r="5" fill="#ff5c8a" />
  </svg>
</template>
