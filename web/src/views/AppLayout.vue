<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TopBar from '@/components/common/TopBar.vue'
import { useChatStore } from '@/stores/chat'

const route = useRoute()
const chat = useChatStore()
const isHome = computed(() => route.name === 'home')
const title = computed(() => (route.name === 'chat' ? chat.conversation?.title ?? null : null))
</script>

<template>
  <div class="relative flex h-full flex-col">
    <!-- 首页：顶栏浮在可滚动的落地页之上（插画背景在首页首屏内部） -->
    <TopBar :title="title" :minimal="isHome" :landing="isHome" :class="isHome ? 'absolute inset-x-0 top-0' : ''" />
    <main class="relative min-h-0 flex-1">
      <RouterView />
    </main>
  </div>
</template>
