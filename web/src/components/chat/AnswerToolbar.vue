<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, Copy, Download, FileSearch, Loader2 } from 'lucide-vue-next'
import type { ArtifactFormat, ArtifactPart, MessageOut, TextPart } from '@/api/types'
import { FORMAT_LABEL, downloadFormat, partFormats, previewArtifactId } from '@/lib/artifactFormats'
import { usePanelStore } from '@/stores/panel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ message: MessageOut; part: TextPart }>()
const panel = usePanelStore()
const toast = useToastStore()
const copied = ref(false)
const busy = ref<string | null>(null)

/** 同一消息中带多格式的成果（优先报告） */
const deliverable = computed<ArtifactPart | null>(() => {
  const arts = props.message.parts.filter((p) => p.type === 'artifact') as ArtifactPart[]
  const withFormats = arts.filter((a) => a.formats?.length)
  return withFormats.find((a) => a.artifact_kind === 'report') ?? withFormats[0] ?? null
})
const formats = computed(() => (deliverable.value ? partFormats(deliverable.value) : []))

async function copy() {
  try {
    await navigator.clipboard.writeText(props.part.text)
  } catch {
    // 非安全上下文的兜底
    const ta = document.createElement('textarea')
    ta.value = props.part.text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  copied.value = true
  setTimeout(() => (copied.value = false), 1600)
}

async function dl(f: ArtifactFormat) {
  if (!deliverable.value) return
  busy.value = f.artifact_id
  try {
    await downloadFormat(deliverable.value, f)
  } catch (e) {
    toast.error(e, '下载失败')
  } finally {
    busy.value = null
  }
}

function openReport() {
  const d = deliverable.value
  if (d) panel.openArtifact(previewArtifactId(d), d.task_id, formats.value, d.display_name)
}
</script>

<template>
  <div class="hairline mt-3 flex flex-wrap items-center gap-1.5 border-t pt-2.5" aria-label="回答操作">
    <button class="btn-ghost btn-sm" :aria-label="copied ? '已复制' : '复制回答（Markdown）'" @click="copy">
      <Check v-if="copied" class="h-3.5 w-3.5 text-emerald-500" />
      <Copy v-else class="h-3.5 w-3.5" />
      {{ copied ? '已复制' : '复制' }}
    </button>
    <template v-if="formats.length">
      <span class="mx-1 h-4 w-px bg-white/10" aria-hidden="true" />
      <button
        v-for="f in formats"
        :key="f.artifact_id"
        class="btn-ghost btn-sm"
        :disabled="busy === f.artifact_id"
        :aria-label="`下载 ${FORMAT_LABEL[f.format]}`"
        @click="dl(f)"
      >
        <Loader2 v-if="busy === f.artifact_id" class="h-3.5 w-3.5 animate-spin" />
        <Download v-else class="h-3.5 w-3.5" />
        {{ FORMAT_LABEL[f.format] }}
      </button>
      <div class="flex-1" />
      <button class="btn-secondary btn-sm" @click="openReport"><FileSearch class="h-3.5 w-3.5" /> 查看完整报告</button>
    </template>
  </div>
</template>
