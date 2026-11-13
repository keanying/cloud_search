<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TopBar from '@/components/common/TopBar.vue'
import { useChatStore } from '@/stores/chat'

const route = useRoute()
const chat = useChatStore()
const title = computed(() => (route.name === 'chat' ? chat.conversation?.title ?? null : null))
</script>

<template>
  <div class="flex h-full flex-col">
    <TopBar :title="title" />
    <main class="min-h-0 flex-1">
      <RouterView />
    </main>
  </div>
</template>
