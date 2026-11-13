<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { Loader2, Save } from 'lucide-vue-next'
import type { AgentBindingOut, ModelOut } from '@/api/types'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ bindings: AgentBindingOut[]; models: ModelOut[] }>()
const emit = defineEmits<{ changed: [] }>()
const toast = useToastStore()

interface Draft {
  model_profile_id: string
  fallback_profile_ids: string[]
  temperature: number | null
  max_tokens: number | null
  saving: boolean
}
const drafts = reactive<Record<string, Draft>>({})

watch(
  () => props.bindings,
  (bs) => {
    for (const b of bs) {
      drafts[b.agent_role] = {
        model_profile_id: b.model_profile_id ?? '',
        fallback_profile_ids: [...b.fallback_profile_ids],
        temperature: b.temperature,
        max_tokens: b.max_tokens,
        saving: false,
      }
    }
  },
  { immediate: true },
)

const enabledModels = computed(() => props.models.filter((m) => m.enabled))
const label = (m: ModelOut) => `${m.provider_name ?? ''} · ${m.display_name || m.model_name}`

function toggleFallback(role: string, id: string) {
  const d = drafts[role]
  const i = d.fallback_profile_ids.indexOf(id)
  if (i >= 0) d.fallback_profile_ids.splice(i, 1)
  else d.fallback_profile_ids.push(id)
}

async function save(role: string) {
  const d = drafts[role]
  if (!d.model_profile_id) {
    toast.push('请选择主模型', 'error')
    return
  }
  d.saving = true
  try {
    await api.putAgentBinding(role, {
      model_profile_id: d.model_profile_id,
      fallback_profile_ids: d.fallback_profile_ids.filter((x) => x !== d.model_profile_id),
      temperature: d.temperature === null || Number.isNaN(d.temperature as number) ? null : d.temperature,
      max_tokens: d.max_tokens === null || Number.isNaN(d.max_tokens as number) ? null : d.max_tokens,
    })
    toast.push('已保存绑定', 'success')
    emit('changed')
  } catch (e) {
    toast.error(e)
  } finally {
    d.saving = false
  }
}
</script>

<template>
  <div>
    <p class="mb-3 text-sm text-slate-400">
      每个智能体各司其职，可绑定不同模型：理解与核验建议用强推理模型，抽取与搜索规划可用快速低价模型，报告写作建议用长上下文模型。未绑定的角色使用“默认”绑定。主模型失败时按顺序尝试备用模型。
    </p>
    <div v-if="!enabledModels.length" class="glass mb-3 px-4 py-3 text-sm text-amber-200">请先在“模型”页添加并启用至少一个模型。</div>
    <ul class="space-y-2">
      <li v-for="b in bindings" :key="b.agent_role" class="glass p-5">
        <div class="flex flex-wrap items-baseline gap-2">
          <span class="text-sm font-semibold text-white">{{ b.role_label }}</span>
          <span class="font-mono text-xs text-slate-500">{{ b.agent_role }}</span>
          <span v-if="!b.model_profile_id" class="text-xs text-amber-300">未绑定</span>
        </div>
        <p class="mt-0.5 text-xs text-slate-400">{{ b.description }}</p>
        <div v-if="drafts[b.agent_role]" class="mt-3 grid gap-3 md:grid-cols-[2fr_1fr_1fr_auto] md:items-end">
          <div>
            <label class="label" :for="`bm-${b.agent_role}`">主模型</label>
            <select :id="`bm-${b.agent_role}`" v-model="drafts[b.agent_role].model_profile_id" class="input">
              <option value="">— 选择模型 —</option>
              <option v-for="m in enabledModels" :key="m.model_profile_id" :value="m.model_profile_id">{{ label(m) }}</option>
            </select>
          </div>
          <div>
            <label class="label" :for="`bt-${b.agent_role}`">温度</label>
            <input :id="`bt-${b.agent_role}`" v-model.number="drafts[b.agent_role].temperature" type="number" min="0" max="2" step="0.1" class="input" placeholder="默认" />
          </div>
          <div>
            <label class="label" :for="`bx-${b.agent_role}`">最大输出 token</label>
            <input :id="`bx-${b.agent_role}`" v-model.number="drafts[b.agent_role].max_tokens" type="number" min="1" class="input" placeholder="默认" />
          </div>
          <button class="btn-primary btn-sm h-9" :disabled="drafts[b.agent_role].saving" @click="save(b.agent_role)">
            <Loader2 v-if="drafts[b.agent_role].saving" class="h-3.5 w-3.5 animate-spin" />
            <Save v-else class="h-3.5 w-3.5" /> 保存
          </button>
        </div>
        <div v-if="drafts[b.agent_role] && enabledModels.length > 1" class="mt-3">
          <div class="label">备用模型（按选择顺序）</div>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="m in enabledModels.filter((x) => x.model_profile_id !== drafts[b.agent_role].model_profile_id)"
              :key="m.model_profile_id"
              type="button"
              class="rounded-full border px-2.5 py-1 text-xs"
              :class="drafts[b.agent_role].fallback_profile_ids.includes(m.model_profile_id) ? 'chip-active' : 'border-white/15 text-slate-400 hover:text-white'"
              :aria-pressed="drafts[b.agent_role].fallback_profile_ids.includes(m.model_profile_id)"
              @click="toggleFallback(b.agent_role, m.model_profile_id)"
            >
              <template v-if="drafts[b.agent_role].fallback_profile_ids.includes(m.model_profile_id)">
                {{ drafts[b.agent_role].fallback_profile_ids.indexOf(m.model_profile_id) + 1 }}.
              </template>
              {{ label(m) }}
            </button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
