<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Grip } from 'lucide-vue-next'
import { runHomeAction, visibleActions, type HomeAction } from '@/lib/homeActions'
import { useFloating } from '@/lib/useFloating'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const open = ref(false)
const anchor = ref<HTMLElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const { style } = useFloating(anchor, menu, open, () => 'bottom-end')
const actions = computed(() => visibleActions(!!auth.user?.is_admin, 'launcher'))

function run(a: HomeAction) {
  open.value = false
  runHomeAction(a, router, () => ui.openHistory())
}
</script>

<template>
  <div ref="anchor">
    <button class="icon-btn" aria-label="应用" title="应用" :aria-expanded="open" aria-haspopup="menu" @click="open = !open">
      <Grip class="h-[18px] w-[18px]" />
    </button>
  </div>
  <Teleport to="body">
    <div v-if="open" ref="menu" role="menu" class="popover-menu w-[288px] p-3" :style="style">
      <div class="grid grid-cols-3 gap-1">
        <button
          v-for="a in actions"
          :key="a.key"
          role="menuitem"
          class="flex flex-col items-center gap-1.5 rounded-xl px-1 py-3 text-xs text-slate-200 transition hover:bg-white/5"
          @click="run(a)"
        >
          <span class="flex h-10 w-10 items-center justify-center rounded-full" :class="a.tint">
            <component :is="a.icon" class="h-5 w-5" :class="a.color" />
          </span>
          {{ a.label }}
        </button>
      </div>
    </div>
  </Teleport>
</template>
