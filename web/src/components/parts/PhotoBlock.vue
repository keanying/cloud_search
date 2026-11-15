<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ImageOff } from 'lucide-vue-next'
import { api } from '@/api/client'
import { captionHtml } from '@/lib/markdown'

/** 报告配图（```photo）：来源网页里的图片，写报告时已下载到私有存储，这里带登录凭据读取后显示。 */
const props = defineProps<{ raw: string; fig?: number }>()
const spec = computed(() => {
  try {
    const p = JSON.parse(props.raw) as { task_id?: string; name?: string; caption?: string; credit?: string }
    return p && p.task_id && p.name ? p : null
  } catch {
    return null
  }
})
const url = ref<string | null>(null)
const failed = ref(false)

watch(
  spec,
  async (p) => {
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = null
    failed.value = false
    if (!p) return
    try {
      url.value = URL.createObjectURL(await api.taskFigure(p.task_id!, p.name!))
    } catch {
      failed.value = true
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  if (url.value) URL.revokeObjectURL(url.value)
})
const caption = computed(() => {
  const p = spec.value
  if (!p) return ''
  const head = `${props.fig ? `图${props.fig}｜` : ''}${p.caption || ''}`
  const sep = /[。？！?!.]$/.test(head) ? '' : '。'
  return captionHtml(p.credit ? `${head}${sep}${p.credit}` : head)
})
</script>

<template>
  <figure v-if="spec" class="not-prose my-5">
    <div class="photo-frame">
      <img v-if="url" :src="url" :alt="spec.caption || '报告配图'" class="mx-auto block max-h-[420px] w-auto max-w-full object-contain" />
      <div v-else class="flex h-40 items-center justify-center gap-2 text-sm text-slate-500">
        <ImageOff v-if="failed" class="h-4 w-4" /> {{ failed ? '图片加载失败' : '加载图片…' }}
      </div>
    </div>
    <!-- eslint-disable-next-line vue/no-v-html -- 已转义，仅插入引用按钮 -->
    <figcaption class="mt-2 text-center text-[12px] leading-5 text-slate-400" v-html="caption" />
  </figure>
</template>

<style scoped>
.photo-frame {
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid var(--cs-line);
  background: var(--cs-surface-sunken);
  box-shadow: var(--cs-shadow);
}
</style>
