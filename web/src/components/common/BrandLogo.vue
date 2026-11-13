<script setup lang="ts">
defineProps<{ size?: number }>()
</script>

<template>
  <svg :width="size ?? 32" :height="size ?? 32" viewBox="0 0 64 64" aria-hidden="true">
    <defs>
      <linearGradient id="cs-logo-g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#7dd3fc" />
        <stop offset="1" stop-color="#2563eb" />
      </linearGradient>
    </defs>
    <circle cx="32" cy="32" r="28" fill="url(#cs-logo-g)" />
    <circle cx="32" cy="32" r="13" fill="#0b1e46" />
    <circle cx="36" cy="28" r="5" fill="#e0f2fe" />
  </svg>
</template>
