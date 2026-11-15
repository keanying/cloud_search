<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { X } from 'lucide-vue-next'

/** 右侧抽屉：编辑表单等。Esc / 点遮罩关闭；内容区滚动，底部固定操作栏（#footer） */
const props = withDefaults(defineProps<{ title: string; desc?: string; width?: number }>(), { desc: '', width: 560 })
const open = defineModel<boolean>({ default: false })

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}
watch(
  open,
  (v) => {
    if (v) document.addEventListener('keydown', onKey)
    else document.removeEventListener('keydown', onKey)
  },
  { immediate: true },
)
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
void props
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="open" class="fixed inset-0 z-[900] flex justify-end" role="dialog" aria-modal="true" :aria-label="title">
        <div class="drawer-mask absolute inset-0" @click="open = false" />
        <section
          class="drawer-panel relative flex h-full w-full flex-col"
          :style="{ maxWidth: `${width}px` }"
        >
          <header class="hairline flex items-start gap-3 border-b px-6 py-4">
            <div class="min-w-0 flex-1">
              <slot name="title">
                <h2 class="text-base font-bold tracking-tight text-white">{{ title }}</h2>
                <p v-if="desc" class="mt-0.5 text-[13px] text-slate-400">{{ desc }}</p>
              </slot>
            </div>
            <slot name="headerActions" />
            <button type="button" class="icon-btn" aria-label="关闭" @click="open = false"><X class="h-4 w-4" /></button>
          </header>
          <slot name="tabs" />
          <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5"><slot /></div>
          <footer v-if="$slots.footer" class="hairline flex items-center justify-end gap-2 border-t px-6 py-4">
            <slot name="footer" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer-mask {
  background: rgb(20 22 45 / 0.28);
  backdrop-filter: blur(3px);
}
.drawer-panel {
  background: var(--cs-surface-solid);
  box-shadow: var(--cs-shadow-lg);
  border-left: 1px solid var(--cs-rim);
  backdrop-filter: var(--cs-blur);
  -webkit-backdrop-filter: var(--cs-blur);
  border-top-left-radius: 26px;
  border-bottom-left-radius: 26px;
}
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.2s ease;
}
.drawer-enter-active .drawer-panel,
.drawer-leave-active .drawer-panel {
  transition: transform 0.24s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from .drawer-panel,
.drawer-leave-to .drawer-panel {
  transform: translateX(40px);
}
</style>
