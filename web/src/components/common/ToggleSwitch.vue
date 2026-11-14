<script setup lang="ts">
/** 开关（role=switch） */
defineProps<{ label?: string; disabled?: boolean; small?: boolean }>()
const on = defineModel<boolean>({ default: false })
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="on"
    :aria-label="label"
    :disabled="disabled"
    class="relative inline-flex shrink-0 items-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-50"
    :class="[small ? 'h-5 w-9' : 'h-7 w-12', on ? 'bg-[var(--cs-ink)]' : 'bg-slate-500/40']"
    @click.stop="on = !on"
  >
    <span
      class="inline-block rounded-full shadow transition"
      :class="[
        small ? 'h-3.5 w-3.5' : 'h-5 w-5',
        on ? (small ? 'translate-x-[18px]' : 'translate-x-6') + ' bg-[var(--cs-on-ink)]' : 'translate-x-1 bg-[#fff]',
      ]"
    />
  </button>
</template>
