<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

/** 有未保存修改时吸附在底部的保存条 */
defineProps<{ count: number; saving: boolean }>()
const emit = defineEmits<{ save: []; discard: [] }>()
</script>

<template>
  <Transition name="savebar">
    <div v-if="count" class="sticky bottom-4 z-20 mt-6 flex justify-center">
      <div class="savebar flex items-center gap-3 rounded-full py-2 pr-2 pl-5" role="status">
        <span class="h-2 w-2 rounded-full bg-[var(--pastel-butter-dot)]" />
        <span class="text-sm font-medium">有 {{ count }} 项修改尚未保存</span>
        <button type="button" class="savebar-ghost" :disabled="saving" @click="emit('discard')">放弃</button>
        <button type="button" class="savebar-primary" :disabled="saving" @click="emit('save')">
          <Loader2 v-if="saving" class="h-3.5 w-3.5 animate-spin" /> 保存修改
        </button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.savebar {
  background: var(--cs-bar);
  color: var(--cs-on-bar);
  box-shadow: var(--cs-shadow-lg);
}
.savebar-ghost,
.savebar-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 999px;
  padding: 0.45rem 1rem;
  font-size: 13px;
  font-weight: 600;
}
.savebar-ghost {
  color: rgb(244 244 240 / 0.75);
}
.savebar-ghost:hover {
  background: rgb(255 255 255 / 0.08);
}
.savebar-primary {
  background: #f4f4f0;
  color: #111214;
}
.savebar-enter-active,
.savebar-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.savebar-enter-from,
.savebar-leave-to {
  opacity: 0;
  transform: translateY(12px);
}
</style>
