<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import type { HomeArt } from '@/stores/prefs'

// 每种插画按需加载，主包不包含插画
const ARTS = {
  glass: defineAsyncComponent(() => import('./GlassArt.vue')),
  hills: defineAsyncComponent(() => import('./HillsArt.vue')),
  pond: defineAsyncComponent(() => import('./PondArt.vue')),
  night: defineAsyncComponent(() => import('./NightArt.vue')),
}
const props = defineProps<{ art: HomeArt }>()
const comp = computed(() => (props.art === 'plain' ? null : ARTS[props.art]))
</script>

<template>
  <div class="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
    <component :is="comp" v-if="comp" />
  </div>
</template>
