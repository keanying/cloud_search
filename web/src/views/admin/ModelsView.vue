<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { CircleCheck, CircleX, FlaskConical, Loader2, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import type { ModelOut, ModelTestOut } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import ChipSelect from '@/components/common/ChipSelect.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import SideDrawer from '@/components/common/SideDrawer.vue'
import ToggleSwitch from '@/components/common/ToggleSwitch.vue'
import { compact } from '@/lib/adminFormat'
import { useAdminLlmStore } from '@/stores/adminLlm'
import { useToastStore } from '@/stores/toast'

const store = useAdminLlmStore()
const toast = useToastStore()
onMounted(() => store.load().catch((e) => toast.error(e, '加载配置失败')))

const q = ref('')
const providerFilter = ref('')
const providerOptions = computed(() => store.providers.map((p) => ({ value: p.provider_id, label: p.provider_name })))
const rows = computed(() => {
  const k = q.value.toLowerCase()
  return store.models.filter(
    (m) =>
      (!providerFilter.value || m.provider_id === providerFilter.value) &&
      (!k || `${m.model_name} ${m.display_name ?? ''} ${m.provider_name ?? ''}`.toLowerCase().includes(k)),
  )
})

const testing = ref<Record<string, boolean>>({})
const results = ref<Record<string, ModelTestOut>>({})
const detail = ref<ModelOut | null>(null)

const formOpen = ref(false)
const editing = ref<ModelOut | null>(null)
const saving = ref(false)
/** 价格在界面以“元/百万 token”输入，提交时换算为“分” */
const blank = () => ({
  provider_id: store.providers[0]?.provider_id ?? '',
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
const form = reactive(blank())
const exampleModels = computed(() => {
  const prov = store.providers.find((p) => p.provider_id === form.provider_id)
  return store.presets.find((x) => x.provider_type === prov?.provider_type)?.example_models ?? []
})
const toFen = (y: number | null) => (y == null || Number.isNaN(y) ? null : Math.round(y * 100))
const toYuan = (f: number | null) => (f == null ? null : f / 100)
const numOrNull = (v: unknown) => (v === '' || v == null || Number.isNaN(Number(v)) ? null : Number(v))

const CAPS = [
  { key: 'supports_tools', label: '工具调用', help: '优先用工具调用输出结构化结果' },
  { key: 'supports_forced_tool_choice', label: '强制工具调用', help: '思考模式模型（如 DeepSeek V4、Kimi K2.5+）通常不支持；不确定可保持开启，首次被拒时会自动关闭' },
  { key: 'supports_json_schema', label: '严格 JSON Schema', help: '原生结构化输出' },
  { key: 'supports_json_object', label: 'JSON 模式', help: 'response_format=json_object' },
  { key: 'supports_vision', label: '图片输入', help: '多模态输入' },
] as const

const columns: Column[] = [
  { key: 'model', title: '模型', minWidth: 240, width: 280, fixed: 'left' },
  { key: 'provider_name', title: '供应方', width: 140 },
  { key: 'caps', title: '能力', minWidth: 260 },
  { key: 'context_window_qty', title: '上下文', width: 100, align: 'right', sortable: true },
  { key: 'price', title: '单价（元/百万 token）', width: 190, align: 'right' },
  { key: 'test', title: '连通测试', width: 150 },
  { key: 'enabled', title: '启用', width: 80, align: 'center' },
  { key: 'actions', title: '', width: 100, align: 'right', fixed: 'right' },
]

function openAdd() {
  editing.value = null
  Object.assign(form, blank())
  formOpen.value = true
}
function openEdit(m: ModelOut) {
  editing.value = m
  Object.assign(form, {
    ...blank(),
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
    await store.load(true)
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
    if (results.value[m.model_profile_id].adaptations?.length) await store.load(true)
  } catch (e) {
    results.value[m.model_profile_id] = { ok: false, latency_ms: null, reply: null, error: e instanceof Error ? e.message : '测试失败' }
  } finally {
    testing.value[m.model_profile_id] = false
  }
}
async function toggle(m: ModelOut, v: boolean) {
  try {
    await api.patchModel(m.model_profile_id, { enabled: v })
    await store.load(true)
  } catch (e) {
    toast.error(e)
  }
}
async function remove(m: ModelOut) {
  if (!confirm(`删除模型「${m.display_name || m.model_name}」？绑定它的智能体需要重新选择模型。`)) return
  try {
    await api.deleteModel(m.model_profile_id)
    toast.push('已删除', 'success')
    await store.load(true)
  } catch (e) {
    toast.error(e)
  }
}
const yuan = (f: number | null) => (f == null ? '?' : (f / 100).toFixed(2))
</script>

<template>
  <AdminPage>
    <template #actions>
      <button class="btn-primary" :disabled="!store.providers.length" @click="openAdd"><Plus class="h-4 w-4" /> 添加模型</button>
    </template>

    <FilterBar v-model:q="q" placeholder="搜索模型名或显示名称">
      <ChipSelect v-if="providerOptions.length > 1" v-model="providerFilter" label="供应方" :options="providerOptions" />
    </FilterBar>

    <DataTable
      :columns="columns"
      :rows="rows"
      row-key="model_profile_id"
      :loading="store.loading"
      :empty-text="store.providers.length ? '还没有模型' : '请先添加供应方'"
      empty-desc="能力矩阵决定结构化输出方式：支持工具调用优先用工具输出，否则退回 JSON 模式或提示词约束"
    >
      <template #cell-model="{ row }">
        <div class="min-w-0 leading-tight">
          <div class="truncate font-semibold text-white">{{ row.display_name || row.model_name }}</div>
          <div class="truncate font-mono text-[11px] text-slate-500">{{ row.model_name }}</div>
        </div>
      </template>
      <template #cell-caps="{ row }">
        <span class="flex flex-wrap gap-1">
          <span v-if="row.supports_tools" class="pill card-mint accent-ink">工具</span>
          <span v-if="row.supports_tools && !row.supports_forced_tool_choice" class="pill card-butter accent-ink" title="思考模式：工具调用改为自动选择">非强制</span>
          <span v-if="row.supports_json_schema" class="pill card-sky accent-ink">Schema</span>
          <span v-if="row.supports_json_object" class="pill card-sky accent-ink">JSON</span>
          <span v-if="row.supports_vision" class="pill card-lilac accent-ink">图片</span>
        </span>
      </template>
      <template #cell-context_window_qty="{ row }"><span class="tabular-nums">{{ compact(row.context_window_qty) }}</span></template>
      <template #cell-price="{ row }">
        <span class="tabular-nums" :class="row.input_price_minor_amt == null ? 'text-amber-300' : 'text-slate-200'" :title="row.input_price_minor_amt == null ? '单价未知：调用记为待核算，不按 0 计' : ''">
          {{ yuan(row.input_price_minor_amt) }} / {{ yuan(row.output_price_minor_amt) }}
        </span>
        <span class="ml-1 text-[11px] text-slate-500">{{ row.currency_code }}</span>
      </template>
      <template #cell-test="{ row }">
        <span class="inline-flex items-center gap-1.5">
          <button class="btn-secondary btn-sm" :disabled="testing[row.model_profile_id]" @click="test(row)">
            <Loader2 v-if="testing[row.model_profile_id]" class="h-3.5 w-3.5 animate-spin" />
            <FlaskConical v-else class="h-3.5 w-3.5" /> 测试
          </button>
          <button
            v-if="results[row.model_profile_id]"
            type="button"
            class="inline-flex items-center"
            :title="results[row.model_profile_id].ok ? `成功 · ${results[row.model_profile_id].latency_ms} ms` : results[row.model_profile_id].error ?? '失败'"
            :aria-label="results[row.model_profile_id].ok ? '测试成功，查看详情' : '测试失败，查看详情'"
            @click="detail = row"
          >
            <CircleCheck v-if="results[row.model_profile_id].ok" class="h-4.5 w-4.5 text-emerald-300" />
            <CircleX v-else class="h-4.5 w-4.5 text-rose-300" />
          </button>
        </span>
      </template>
      <template #cell-enabled="{ row }">
        <ToggleSwitch small :model-value="row.enabled" :label="`启用 ${row.model_name}`" @update:model-value="(v: boolean) => toggle(row, v)" />
      </template>
      <template #cell-actions="{ row }">
        <span class="inline-flex gap-0.5">
          <button class="icon-btn !h-8 !w-8" aria-label="编辑" title="编辑" @click="openEdit(row)"><Pencil class="h-4 w-4" /></button>
          <button class="icon-btn !h-8 !w-8 hover:!text-rose-300" aria-label="删除" title="删除" @click="remove(row)"><Trash2 class="h-4 w-4" /></button>
        </span>
      </template>
    </DataTable>

    <!-- 测试结果详情 -->
    <SideDrawer
      :model-value="!!detail"
      :title="detail ? `测试结果：${detail.display_name || detail.model_name}` : ''"
      :width="480"
      @update:model-value="(v: boolean) => !v && (detail = null)"
    >
      <template v-if="detail && results[detail.model_profile_id]">
        <div class="rounded-2xl p-4 text-sm" :class="results[detail.model_profile_id].ok ? 'card-mint accent-ink' : 'card-peach accent-ink'">
          <template v-if="results[detail.model_profile_id].ok">
            <div class="font-semibold">连通成功 · 结构化输出可用</div>
            <div class="mt-1">耗时 {{ results[detail.model_profile_id].latency_ms }} ms</div>
          </template>
          <template v-else>
            <div class="font-semibold">
              {{ results[detail.model_profile_id].reply ? `连通成功（${results[detail.model_profile_id].latency_ms} ms），但结构化输出失败` : '测试失败' }}
            </div>
            <div class="mt-1 break-words">{{ results[detail.model_profile_id].error }}</div>
          </template>
        </div>
        <div v-if="results[detail.model_profile_id].reply" class="mt-4">
          <div class="label">模型回复</div>
          <div class="rounded-2xl sunken p-3 text-sm whitespace-pre-wrap">{{ results[detail.model_profile_id].reply }}</div>
        </div>
        <div v-if="results[detail.model_profile_id].adaptations?.length" class="mt-4">
          <div class="label">已自动调整的能力配置</div>
          <ul class="space-y-1.5 text-sm">
            <li v-for="a in results[detail.model_profile_id].adaptations" :key="a" class="rounded-xl card-butter px-3 py-2 accent-ink">{{ a }}</li>
          </ul>
        </div>
      </template>
    </SideDrawer>

    <!-- 添加 / 编辑 -->
    <SideDrawer v-model="formOpen" :title="editing ? `编辑模型：${editing.display_name || editing.model_name}` : '添加模型'" :width="620">
      <form id="model-form" class="space-y-5" @submit.prevent="save">
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="mp">供应方</label>
            <select id="mp" v-model="form.provider_id" class="input" :disabled="!!editing">
              <option v-for="p in store.providers" :key="p.provider_id" :value="p.provider_id">{{ p.provider_name }}</option>
            </select>
          </div>
          <div>
            <label class="label" for="md">显示名称</label>
            <input id="md" v-model="form.display_name" class="input" placeholder="可选" />
          </div>
          <div class="sm:col-span-2">
            <label class="label" for="mn">模型名 / 接入点 ID</label>
            <input id="mn" v-model="form.model_name" class="input font-mono" list="cs-model-examples" :disabled="!!editing" required />
            <datalist id="cs-model-examples">
              <option v-for="x in exampleModels" :key="x" :value="x" />
            </datalist>
            <div v-if="exampleModels.length && !editing" class="mt-2 flex flex-wrap gap-1.5">
              <button v-for="x in exampleModels" :key="x" type="button" class="chip !px-2.5 !py-0.5 !text-xs font-mono" @click="form.model_name = x">{{ x }}</button>
            </div>
          </div>
        </div>
        <fieldset>
          <legend class="label">能力</legend>
          <div class="divide-y overflow-hidden rounded-2xl sunken [&>*]:border-[var(--cs-line)]">
            <label v-for="c in CAPS" :key="c.key" class="flex items-center gap-3 px-4 py-2.5">
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-semibold text-white">{{ c.label }}</span>
                <span class="block text-xs text-slate-500">{{ c.help }}</span>
              </span>
              <ToggleSwitch
                v-model="form[c.key]"
                small
                :label="c.label"
                :disabled="c.key === 'supports_forced_tool_choice' && !form.supports_tools"
              />
            </label>
          </div>
        </fieldset>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="mc">上下文长度</label>
            <input id="mc" v-model.number="form.context_window_qty" type="number" min="0" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mo">最大输出 token</label>
            <input id="mo" v-model.number="form.max_output_qty" type="number" min="0" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mi">输入价（元/百万 token）</label>
            <input id="mi" v-model.number="form.input_price_yuan" type="number" min="0" step="0.01" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mout">输出价（元/百万 token）</label>
            <input id="mout" v-model.number="form.output_price_yuan" type="number" min="0" step="0.01" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mcur">币种</label>
            <input id="mcur" v-model="form.currency_code" class="input" maxlength="8" />
          </div>
          <label class="flex items-end justify-between gap-3 pb-2.5 text-sm">
            <span class="font-semibold text-white">启用</span>
            <ToggleSwitch v-model="form.enabled" label="启用" />
          </label>
        </div>
        <p class="text-xs text-slate-500">单价未知的调用记为“待核算”，不按 0 计入费用。</p>
      </form>
      <template #footer>
        <button type="button" class="btn-ghost" @click="formOpen = false">取消</button>
        <button type="submit" form="model-form" class="btn-primary" :disabled="saving">保存</button>
      </template>
    </SideDrawer>
  </AdminPage>
</template>
