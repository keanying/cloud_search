<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import type { AgentBindingOut, ModelOut, ProviderOut, ProviderPreset } from '@/api/types'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toast'
import ProvidersTab from '@/components/admin/ProvidersTab.vue'
import ModelsTab from '@/components/admin/ModelsTab.vue'
import BindingsTab from '@/components/admin/BindingsTab.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatTiles from '@/components/task/StatTiles.vue'

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
    <div class="mx-auto max-w-5xl px-4 pt-6 pb-12 md:px-6">
      <PageHeader
        title="管理后台"
        desc="配置 OpenAI、DeepSeek、Kimi、火山方舟、通义千问、智谱等供应方，并为八个智能体分别绑定模型。"
        :parent="{ name: 'settings' }"
      >
        <StatTiles
          v-if="!loading"
          class="w-full sm:w-[360px]"
          :items="[
            { label: '供应方', value: providers.length, tone: 'sky' },
            { label: '模型', value: models.length, tone: 'lilac' },
            { label: '智能体绑定', value: bindings.length, tone: 'mint' },
          ]"
        />
      </PageHeader>
      <div class="sunken hairline mb-5 inline-flex gap-0.5 rounded-full border p-1" role="tablist">
        <button
          v-for="t in TABS"
          :key="t.v"
          role="tab"
          :aria-selected="tab === t.v"
          class="rounded-full px-4 py-1.5 text-sm font-semibold"
          :class="tab === t.v ? 'chip-active' : 'text-slate-400 hover:text-white'"
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
