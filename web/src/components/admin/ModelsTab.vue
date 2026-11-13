<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { FlaskConical, Loader2, Pencil, Plus, Trash2, X } from 'lucide-vue-next'
import type { ModelOut, ModelTestOut, ProviderOut, ProviderPreset } from '@/api/types'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toast'
import EmptyState from '@/components/common/EmptyState.vue'

const props = defineProps<{ providers: ProviderOut[]; models: ModelOut[]; presets: ProviderPreset[] }>()
const emit = defineEmits<{ changed: [] }>()
const toast = useToastStore()

const formOpen = ref(false)
const editing = ref<ModelOut | null>(null)
const saving = ref(false)
const testing = ref<Record<string, boolean>>({})
const results = ref<Record<string, ModelTestOut>>({})

/** 价格在界面以“元/百万 token”输入，提交时换算为“分” */
const form = reactive({
  provider_id: '',
  model_name: '',
  display_name: '',
  supports_tools: true,
  supports_forced_tool_choice: true,
  supports_json_schema: false,
  supports_json_object: true,
  supports_vision: false,
  context_window_qty: null as number | null,
  max_output_qty: null as number | null,
  input_price_yuan: null as number | null,
  output_price_yuan: null as number | null,
  currency_code: 'CNY',
  enabled: true,
})

const providerName = (id: string) => props.providers.find((p) => p.provider_id === id)?.provider_name ?? id
const exampleModels = computed(() => {
  const prov = props.providers.find((p) => p.provider_id === form.provider_id)
  return props.presets.find((x) => x.provider_type === prov?.provider_type)?.example_models ?? []
})

const toFen = (y: number | null) => (y == null || Number.isNaN(y) ? null : Math.round(y * 100))
const toYuan = (f: number | null) => (f == null ? null : f / 100)
const numOrNull = (v: unknown) => (v === '' || v == null || Number.isNaN(Number(v)) ? null : Number(v))

function openAdd() {
  editing.value = null
  Object.assign(form, {
    provider_id: props.providers[0]?.provider_id ?? '',
    model_name: '',
    display_name: '',
    supports_tools: true,
    supports_forced_tool_choice: true,
    supports_json_schema: false,
    supports_json_object: true,
    supports_vision: false,
    context_window_qty: null,
    max_output_qty: null,
    input_price_yuan: null,
    output_price_yuan: null,
    currency_code: 'CNY',
    enabled: true,
  })
  formOpen.value = true
}
function openEdit(m: ModelOut) {
  editing.value = m
  Object.assign(form, {
    provider_id: m.provider_id,
    model_name: m.model_name,
    display_name: m.display_name ?? '',
    supports_tools: m.supports_tools,
    supports_forced_tool_choice: m.supports_forced_tool_choice,
    supports_json_schema: m.supports_json_schema,
    supports_json_object: m.supports_json_object,
    supports_vision: m.supports_vision,
    context_window_qty: m.context_window_qty,
    max_output_qty: m.max_output_qty,
    input_price_yuan: toYuan(m.input_price_minor_amt),
    output_price_yuan: toYuan(m.output_price_minor_amt),
    currency_code: m.currency_code,
    enabled: m.enabled,
  })
  formOpen.value = true
}

async function save() {
  if (!form.provider_id || !form.model_name.trim()) {
    toast.push('请选择供应方并填写模型名', 'error')
    return
  }
  const common = {
    display_name: form.display_name.trim() || null,
    supports_tools: form.supports_tools,
    supports_forced_tool_choice: form.supports_forced_tool_choice,
    supports_json_schema: form.supports_json_schema,
    supports_json_object: form.supports_json_object,
    supports_vision: form.supports_vision,
    context_window_qty: numOrNull(form.context_window_qty),
    max_output_qty: numOrNull(form.max_output_qty),
    input_price_minor_amt: toFen(numOrNull(form.input_price_yuan)),
    output_price_minor_amt: toFen(numOrNull(form.output_price_yuan)),
    currency_code: form.currency_code || 'CNY',
    enabled: form.enabled,
  }
  saving.value = true
  try {
    if (editing.value) await api.patchModel(editing.value.model_profile_id, common)
    else await api.createModel({ provider_id: form.provider_id, model_name: form.model_name.trim(), ...common })
    formOpen.value = false
    toast.push('已保存', 'success')
    emit('changed')
  } catch (e) {
    toast.error(e)
  } finally {
    saving.value = false
  }
}

async function test(m: ModelOut) {
  testing.value[m.model_profile_id] = true
  try {
    results.value[m.model_profile_id] = await api.testModel(m.model_profile_id)
  } catch (e) {
    results.value[m.model_profile_id] = { ok: false, latency_ms: null, reply: null, error: e instanceof Error ? e.message : '测试失败' }
  } finally {
    testing.value[m.model_profile_id] = false
  }
}

async function toggle(m: ModelOut) {
  try {
    await api.patchModel(m.model_profile_id, { enabled: !m.enabled })
    emit('changed')
  } catch (e) {
    toast.error(e)
  }
}

async function remove(m: ModelOut) {
  if (!confirm(`删除模型「${m.display_name || m.model_name}」？绑定它的智能体需要重新选择模型。`)) return
  try {
    await api.deleteModel(m.model_profile_id)
    emit('changed')
  } catch (e) {
    toast.error(e)
  }
}

function price(f: number | null, cur: string) {
  return f == null ? '单价未知' : `${(f / 100).toFixed(2)} ${cur === 'CNY' ? '元' : cur}`
}
</script>

<template>
  <div>
    <div class="mb-3 flex items-center justify-between gap-3">
      <p class="text-sm text-slate-400">
        能力矩阵决定结构化输出方式：支持工具调用优先用工具输出，否则退回 JSON 模式或提示词约束。单价未知的调用记为“待核算”，不按 0 计。
      </p>
      <button class="btn-primary btn-sm shrink-0" :disabled="!providers.length" @click="openAdd"><Plus class="h-3.5 w-3.5" /> 添加模型</button>
    </div>

    <form v-if="formOpen" class="glass mb-4 space-y-3 p-6" @submit.prevent="save">
      <div class="flex items-center justify-between">
        <h3 class="card-title">{{ editing ? `编辑：${editing.display_name || editing.model_name}` : '添加模型' }}</h3>
        <button type="button" class="icon-btn" aria-label="取消" @click="formOpen = false"><X class="h-4 w-4" /></button>
      </div>
      <div class="grid gap-3 md:grid-cols-3">
        <div>
          <label class="label" for="mp">供应方</label>
          <select id="mp" v-model="form.provider_id" class="input" :disabled="!!editing">
            <option v-for="p in providers" :key="p.provider_id" :value="p.provider_id">{{ p.provider_name }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="mn">模型名 / 接入点 ID</label>
          <input id="mn" v-model="form.model_name" class="input font-mono" list="cs-model-examples" :disabled="!!editing" required />
          <datalist id="cs-model-examples">
            <option v-for="x in exampleModels" :key="x" :value="x" />
          </datalist>
        </div>
        <div>
          <label class="label" for="md">显示名称</label>
          <input id="md" v-model="form.display_name" class="input" />
        </div>
      </div>
      <fieldset class="flex flex-wrap gap-x-5 gap-y-2 text-sm">
        <legend class="label">能力</legend>
        <label class="flex items-center gap-1.5"><input v-model="form.supports_tools" type="checkbox" class="accent-blue-500" /> 工具调用</label>
        <label class="flex items-center gap-1.5" title="思考模式模型（如 DeepSeek V4、Kimi K2.5+）通常不支持；不确定可保持勾选，首次被拒时会自动关闭">
          <input v-model="form.supports_forced_tool_choice" type="checkbox" class="accent-blue-500" :disabled="!form.supports_tools" /> 强制工具调用
        </label>
        <label class="flex items-center gap-1.5"><input v-model="form.supports_json_schema" type="checkbox" class="accent-blue-500" /> 严格 JSON Schema</label>
        <label class="flex items-center gap-1.5"><input v-model="form.supports_json_object" type="checkbox" class="accent-blue-500" /> JSON 模式</label>
        <label class="flex items-center gap-1.5"><input v-model="form.supports_vision" type="checkbox" class="accent-blue-500" /> 图片输入</label>
      </fieldset>
      <div class="grid gap-3 md:grid-cols-5">
        <div>
          <label class="label" for="mc">上下文长度</label>
          <input id="mc" v-model.number="form.context_window_qty" type="number" min="0" class="input" />
        </div>
        <div>
          <label class="label" for="mo">最大输出 token</label>
          <input id="mo" v-model.number="form.max_output_qty" type="number" min="0" class="input" />
        </div>
        <div>
          <label class="label" for="mi">输入价（元/百万token）</label>
          <input id="mi" v-model.number="form.input_price_yuan" type="number" min="0" step="0.01" class="input" placeholder="未知" />
        </div>
        <div>
          <label class="label" for="mout">输出价（元/百万token）</label>
          <input id="mout" v-model.number="form.output_price_yuan" type="number" min="0" step="0.01" class="input" placeholder="未知" />
        </div>
        <div>
          <label class="label" for="mcur">币种</label>
          <input id="mcur" v-model="form.currency_code" class="input" maxlength="8" />
        </div>
      </div>
      <label class="flex items-center gap-2 text-sm"><input v-model="form.enabled" type="checkbox" class="accent-blue-500" /> 启用</label>
      <div class="flex gap-2">
        <button type="submit" class="btn-primary btn-sm" :disabled="saving">保存</button>
        <button type="button" class="btn-ghost btn-sm" @click="formOpen = false">取消</button>
      </div>
    </form>

    <EmptyState v-if="!models.length" class="glass" :title="providers.length ? '还没有模型' : '请先添加供应方'" />
    <ul class="space-y-2">
      <li v-for="m in models" :key="m.model_profile_id" class="glass p-5">
        <div class="flex flex-wrap items-center gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-sm font-medium text-white">{{ m.display_name || m.model_name }}</span>
              <span class="font-mono text-xs text-slate-500">{{ m.model_name }}</span>
              <span class="pill sunken text-slate-400">{{ m.provider_name || providerName(m.provider_id) }}</span>
              <span v-if="!m.enabled" class="text-xs text-amber-300">已停用</span>
            </div>
            <div class="mt-1 flex flex-wrap gap-1.5 text-[11px]">
              <span v-if="m.supports_tools" class="pill card-mint accent-ink">工具调用</span>
              <span v-if="m.supports_tools && !m.supports_forced_tool_choice" class="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-300" title="思考模式：工具调用改为自动选择">非强制</span>
              <span v-if="m.supports_json_schema" class="pill card-mint accent-ink">JSON Schema</span>
              <span v-if="m.supports_json_object" class="pill card-mint accent-ink">JSON 模式</span>
              <span v-if="m.supports_vision" class="pill card-mint accent-ink">图片输入</span>
              <span v-if="m.context_window_qty" class="pill sunken text-slate-400">上下文 {{ m.context_window_qty }}</span>
              <span class="pill sunken text-slate-400">
                输入 {{ price(m.input_price_minor_amt, m.currency_code) }} · 输出 {{ price(m.output_price_minor_amt, m.currency_code) }} /百万token
              </span>
            </div>
          </div>
          <label class="flex items-center gap-1.5 text-xs text-slate-300">
            <input type="checkbox" :checked="m.enabled" class="accent-blue-500" @change="toggle(m)" /> 启用
          </label>
          <button class="btn-secondary btn-sm" :disabled="testing[m.model_profile_id]" @click="test(m)">
            <Loader2 v-if="testing[m.model_profile_id]" class="h-3.5 w-3.5 animate-spin" />
            <FlaskConical v-else class="h-3.5 w-3.5" /> 测试
          </button>
          <button class="icon-btn" aria-label="编辑" @click="openEdit(m)"><Pencil class="h-4 w-4" /></button>
          <button class="icon-btn" aria-label="删除" @click="remove(m)"><Trash2 class="h-4 w-4" /></button>
        </div>
        <div
          v-if="results[m.model_profile_id]"
          class="mt-2 rounded-lg px-3 py-2 text-xs"
          :class="results[m.model_profile_id].ok ? 'bg-emerald-500/10 text-emerald-200' : 'bg-rose-500/10 text-rose-200'"
        >
          <template v-if="results[m.model_profile_id].ok">
            连通成功 · {{ results[m.model_profile_id].latency_ms }} ms · 结构化输出可用 · 回复：{{ results[m.model_profile_id].reply }}
          </template>
          <template v-else>
            <span v-if="results[m.model_profile_id].reply">连通成功（{{ results[m.model_profile_id].latency_ms }} ms），但</span>
            测试失败：{{ results[m.model_profile_id].error }}
          </template>
          <ul v-if="results[m.model_profile_id].adaptations?.length" class="mt-1 list-disc pl-4 text-amber-200">
            <li v-for="a in results[m.model_profile_id].adaptations" :key="a">已自动调整：{{ a }}</li>
          </ul>
        </div>
      </li>
    </ul>
  </div>
</template>
