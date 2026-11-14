<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { X } from 'lucide-vue-next'
import { usePanelStore } from '@/stores/panel'
import BrowserPanel from './BrowserPanel.vue'

/** 居中大窗：只显示云端浏览器画面。Esc / 点空白处 / × 关闭；关闭不影响后台任务。 */
const panel = usePanelStore()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') panel.closeBrowserModal()
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="cs-modal">
      <div
        v-if="panel.modalTaskId"
        class="fixed inset-0 z-[70] flex items-center justify-center bg-black/55 p-4"
        role="dialog"
        aria-modal="true"
        aria-label="云端浏览器"
        @click.self="panel.closeBrowserModal()"
      >
        <div class="browser-window">
          <BrowserPanel :task-id="panel.modalTaskId" bare />
          <button class="close-btn" aria-label="关闭（不影响后台任务）" title="关闭（不影响后台任务）" @click="panel.closeBrowserModal()">
            <X class="h-4 w-4" />
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.browser-window {
  position: relative;
  width: min(94vw, calc((100vh - 6rem) * 1.49), 1500px);
  max-height: calc(100vh - 2rem);
  overflow: hidden;
  border-radius: 16px;
  background: var(--cs-surface-solid);
  box-shadow: 0 30px 80px -20px rgb(0 0 0 / 0.55);
}
.close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  display: inline-flex;
  height: 32px;
  width: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgb(17 18 20 / 0.72);
  color: #fff;
}
.cs-modal-enter-active,
.cs-modal-leave-active {
  transition: opacity 0.15s ease;
}
.cs-modal-enter-from,
.cs-modal-leave-to {
  opacity: 0;
}
</style>
