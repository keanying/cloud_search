<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TopBar from '@/components/common/TopBar.vue'

const route = useRoute()
const isHome = computed(() => route.name === 'home')
</script>

<template>
  <div class="relative flex h-full flex-col">
    <!-- 首页：顶栏浮在可滚动的落地页之上；其他页面：近黑圆角浮条 -->
    <TopBar :landing="isHome" :class="isHome ? 'absolute inset-x-0 top-0' : ''" />
    <main class="relative min-h-0 flex-1">
      <RouterView />
    </main>
  </div>
</template>
