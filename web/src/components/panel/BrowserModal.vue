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
        <div class="flex flex-col items-end gap-2">
          <!-- 关闭按钮放在窗口外面，避免挡住验证操作条右侧的「接手处理 / 完成 / 跳过」 -->
          <button class="close-btn" aria-label="关闭（不影响后台任务）" title="关闭（不影响后台任务）" @click="panel.closeBrowserModal()">
            <X class="h-4 w-4" />
          </button>
          <div class="browser-window">
            <BrowserPanel :task-id="panel.modalTaskId" bare />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.browser-window {
  position: relative;
  width: min(94vw, calc((100vh - 9rem) * 1.49), 1500px);
  max-height: calc(100vh - 4.5rem);
  overflow: auto;
  border-radius: 22px;
  background: var(--cs-surface-solid);
  border: 1px solid var(--cs-rim);
  box-shadow: 0 30px 80px -20px rgb(20 22 60 / 0.55);
  backdrop-filter: var(--cs-blur);
  -webkit-backdrop-filter: var(--cs-blur);
}
.close-btn {
  display: inline-flex;
  height: 32px;
  width: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.92);
  color: #15172a;
  box-shadow: 0 6px 16px -6px rgb(20 22 60 / 0.4);
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
