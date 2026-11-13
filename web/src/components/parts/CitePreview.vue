<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { ExternalLink } from 'lucide-vue-next'
import type { Citation } from '@/api/types'
import { credibilityTone, hostOf } from '@/lib/format'

/** 引用悬停预览：标题、站点、可信度、发布时间与代表性原文摘录 */
const props = defineProps<{ cite: Citation | null; anchor: HTMLElement | null }>()
const emit = defineEmits<{ enter: []; leave: []; open: [n: number] }>()
const box = ref<HTMLElement | null>(null)
const style = ref<Record<string, string>>({ visibility: 'hidden' })
const tone = computed(() => credibilityTone(props.cite?.credibility))

watch(
  () => [props.cite, props.anchor],
  async () => {
    style.value = { visibility: 'hidden' }
    await nextTick()
    const a = props.anchor
    const b = box.value
    if (!a || !b) return
    const r = a.getBoundingClientRect()
    const w = b.offsetWidth
    const h = b.offsetHeight
    const below = r.bottom + 8 + h < window.innerHeight - 8 || r.top - 8 - h < 8
    const left = Math.min(Math.max(r.left + r.width / 2 - w / 2, 8), window.innerWidth - w - 8)
    style.value = {
      top: `${below ? r.bottom + 8 : r.top - 8 - h}px`,
      left: `${left}px`,
      visibility: 'visible',
    }
  },
)
</script>

<template>
  <Teleport to="body">
    <div
      v-if="cite && anchor"
      ref="box"
      class="cite-preview popover-menu"
      :style="style"
      role="tooltip"
      @mouseenter="emit('enter')"
      @mouseleave="emit('leave')"
    >
      <div class="flex items-center gap-2 text-xs muted">
        <span class="cite-chip !m-0 !align-middle">{{ cite.n }}</span>
        <span class="truncate">{{ cite.site_name || hostOf(cite.url) }}</span>
        <span
          v-if="cite.credibility_label"
          class="cred"
          :style="tone ? { background: `var(--pastel-${tone})`, color: `var(--pastel-${tone}-ink)` } : undefined"
        >{{ cite.credibility_label }}</span>
        <span v-if="cite.publish_time_text" class="ml-auto shrink-0">{{ cite.publish_time_text }}</span>
      </div>
      <div class="mt-1.5 line-clamp-2 text-[14px] font-semibold text-white">{{ cite.title || cite.url }}</div>
      <blockquote v-if="cite.quote" class="quote">“{{ cite.quote }}”</blockquote>
      <div class="mt-2 flex items-center gap-3 text-xs">
        <button type="button" class="font-semibold accent-ink hover:underline" @click="emit('open', cite.n)">查看来源详情</button>
        <a :href="cite.url" target="_blank" rel="noopener" class="inline-flex items-center gap-1 muted hover:underline">
          打开原网页 <ExternalLink class="h-3 w-3" />
        </a>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.cite-preview {
  position: fixed;
  z-index: 60;
  width: min(360px, calc(100vw - 16px));
  padding: 0.8rem 0.95rem;
}
.cred {
  flex-shrink: 0;
  border-radius: 999px;
  padding: 0 0.45rem;
  font-size: 11px;
  font-weight: 600;
  background: var(--cs-line);
}
.quote {
  margin-top: 0.5rem;
  padding-left: 0.6rem;
  border-left: 2px solid var(--cs-line-strong);
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
  opacity: 0.85;
}
</style>
