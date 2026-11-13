<script setup lang="ts">
defineProps<{ size?: number }>()
</script>

<template>
  <svg :width="size ?? 32" :height="size ?? 32" viewBox="0 0 64 64" aria-hidden="true">
    <defs>
      <linearGradient id="cs-logo-g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#8b5cf6" />
        <stop offset="1" stop-color="#4f46e5" />
      </linearGradient>
    </defs>
    <rect x="4" y="4" width="56" height="56" rx="16" fill="url(#cs-logo-g)" />
    <circle cx="30" cy="30" r="12" fill="none" stroke="#fff" stroke-width="5" />
    <path d="M39 39 L48 48" stroke="#fff" stroke-width="5" stroke-linecap="round" />
    <circle cx="34" cy="26" r="3.2" fill="#c7d2fe" />
  </svg>
</template>
