<script setup lang="ts">
import { ref } from 'vue'
import { Check, Palette } from 'lucide-vue-next'
import HomeArtLayer from './art/HomeArtLayer.vue'
import { HOME_ARTS, usePrefsStore } from '@/stores/prefs'
import { useFloating } from '@/lib/useFloating'

const prefs = usePrefsStore()
const open = ref(false)
const anchor = ref<HTMLElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const { style } = useFloating(anchor, menu, open, () => 'bottom-end')
</script>

<template>
  <div ref="anchor">
    <button class="icon-btn" aria-label="首页主题" title="首页主题" :aria-expanded="open" @click="open = !open">
      <Palette class="h-[18px] w-[18px]" />
    </button>
  </div>
  <Teleport to="body">
    <div v-if="open" ref="menu" class="popover-menu w-[300px] p-3" :style="style" role="dialog" aria-label="选择首页主题">
      <div class="mb-2 px-1 text-xs font-medium text-slate-400">首页主题</div>
      <div class="grid grid-cols-2 gap-2.5">
        <button
          v-for="a in HOME_ARTS"
          :key="a.value"
          type="button"
          class="group text-left"
          :aria-pressed="prefs.homeArt === a.value"
          @click="prefs.setHomeArt(a.value)"
        >
          <div
            class="relative h-[72px] overflow-hidden rounded-xl border-2 transition"
            :class="prefs.homeArt === a.value ? 'border-brand-500' : 'border-transparent group-hover:border-brand-400/50'"
          >
            <HomeArtLayer v-if="a.value !== 'plain'" :art="a.value" />
            <div v-else class="absolute inset-0 bg-[radial-gradient(60%_80%_at_85%_10%,rgba(167,139,250,.35),transparent),radial-gradient(60%_80%_at_10%_95%,rgba(94,234,212,.3),transparent)] bg-[#f7f8fc]" />
            <span v-if="prefs.homeArt === a.value" class="absolute top-1.5 right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-brand-500 text-snow">
              <Check class="h-3 w-3" />
            </span>
          </div>
          <div class="mt-1 px-0.5 text-xs text-slate-300">{{ a.label }}<span v-if="a.dark" class="ml-1 text-slate-500">· 深色</span></div>
        </button>
      </div>
    </div>
  </Teleport>
</template>
