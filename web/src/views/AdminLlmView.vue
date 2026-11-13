<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import type { AgentBindingOut, ModelOut, ProviderOut, ProviderPreset } from '@/api/types'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toast'
import ProvidersTab from '@/components/admin/ProvidersTab.vue'
import ModelsTab from '@/components/admin/ModelsTab.vue'
import BindingsTab from '@/components/admin/BindingsTab.vue'

const toast = useToastStore()
const tab = ref<'providers' | 'models' | 'bindings'>('providers')
const loading = ref(true)
const presets = ref<ProviderPreset[]>([])
const providers = ref<ProviderOut[]>([])
const models = ref<ModelOut[]>([])
const bindings = ref<AgentBindingOut[]>([])

const TABS = [
  { v: 'providers', label: '供应方' },
  { v: 'models', label: '模型' },
  { v: 'bindings', label: '智能体绑定' },
] as const

async function load() {
  try {
    const [pr, p, m, b] = await Promise.all([
      api.providerPresets().catch(() => [] as ProviderPreset[]),
      api.listProviders(),
      api.listModels(),
      api.agentBindings(),
    ])
    presets.value = pr
    providers.value = p
    models.value = m
    bindings.value = b
  } catch (e) {
    toast.error(e, '加载配置失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="mx-auto max-w-5xl px-4 py-6">
      <h1 class="text-xl font-semibold text-white">模型与智能体</h1>
      <p class="mt-1 text-sm text-slate-400">配置 OpenAI、DeepSeek、Kimi、火山方舟、通义千问、智谱等供应方，并为八个智能体分别绑定模型。</p>
      <div class="mt-4 mb-4 flex gap-1 border-b border-white/10" role="tablist">
        <button
          v-for="t in TABS"
          :key="t.v"
          role="tab"
          :aria-selected="tab === t.v"
          class="-mb-px border-b-2 px-4 py-2 text-sm"
          :class="tab === t.v ? 'border-brand-400 text-white' : 'border-transparent text-slate-400 hover:text-white'"
          @click="tab = t.v"
        >
          {{ t.label }}
        </button>
      </div>
      <div v-if="loading" class="flex items-center gap-2 text-sm text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> 加载中…</div>
      <template v-else>
        <ProvidersTab v-if="tab === 'providers'" :providers="providers" :presets="presets" @changed="load" />
        <ModelsTab v-else-if="tab === 'models'" :providers="providers" :models="models" :presets="presets" @changed="load" />
        <BindingsTab v-else :bindings="bindings" :models="models" @changed="load" />
      </template>
    </div>
  </div>
</template>
