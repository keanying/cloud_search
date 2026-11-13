<script setup lang="ts">
defineProps<{ size?: number }>()
</script>

<template>
  <svg :width="size ?? 32" :height="size ?? 32" viewBox="0 0 64 64" aria-hidden="true">
    <rect x="4" y="4" width="56" height="56" rx="18" fill="#c9efd9" />
    <circle cx="29" cy="29" r="12" fill="#fff" stroke="#111214" stroke-width="5" />
    <path d="M38 38 L47 47" stroke="#111214" stroke-width="5.5" stroke-linecap="round" />
    <circle cx="47" cy="17" r="5" fill="#f2c94c" />
  </svg>
</template>
