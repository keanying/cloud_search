<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TopBar from '@/components/common/TopBar.vue'
import HomeArtLayer from '@/components/home/art/HomeArtLayer.vue'
import { useChatStore } from '@/stores/chat'
import { usePrefsStore } from '@/stores/prefs'

const route = useRoute()
const chat = useChatStore()
const prefs = usePrefsStore()
const isHome = computed(() => route.name === 'home')
const title = computed(() => (route.name === 'chat' ? chat.conversation?.title ?? null : null))
</script>

<template>
  <div class="relative flex h-full flex-col">
    <!-- 首页插画背景：全屏铺底，位于顶栏与内容之后 -->
    <HomeArtLayer v-if="isHome" :art="prefs.homeArt" />
    <TopBar :title="title" :minimal="isHome" />
    <main class="relative min-h-0 flex-1">
      <RouterView />
    </main>
  </div>
</template>
