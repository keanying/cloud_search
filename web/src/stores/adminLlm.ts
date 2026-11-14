import { defineStore } from 'pinia'
import type { AgentBindingOut, ModelOut, ProviderOut, ProviderPreset } from '@/api/types'
import { api } from '@/api/client'

/** 管理后台：供应方 / 模型 / 智能体分工共用的数据（三个页面互相引用） */
export const useAdminLlmStore = defineStore('adminLlm', {
  state: () => ({
    presets: [] as ProviderPreset[],
    providers: [] as ProviderOut[],
    models: [] as ModelOut[],
    bindings: [] as AgentBindingOut[],
    loaded: false,
    loading: false,
  }),
  getters: {
    enabledModels: (s) => s.models.filter((m) => m.enabled),
    modelLabel: (s) => (id: string | null) => {
      const m = s.models.find((x) => x.model_profile_id === id)
      return m ? `${m.provider_name ?? ''} · ${m.display_name || m.model_name}` : '—'
    },
  },
  actions: {
    async load(force = false) {
      if (this.loaded && !force) return
      this.loading = true
      try {
        const [pr, p, m, b] = await Promise.all([
          api.providerPresets().catch(() => [] as ProviderPreset[]),
          api.listProviders(),
          api.listModels(),
          api.agentBindings(),
        ])
        this.presets = pr
        this.providers = p
        this.models = m
        this.bindings = b
        this.loaded = true
      } finally {
        this.loading = false
      }
    },
  },
})
