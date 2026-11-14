<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleCheck, CircleX, FlaskConical, KeyRound, Loader2, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import type { ModelOut, ModelTestOut, ProviderOut } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import SideDrawer from '@/components/common/SideDrawer.vue'
import ToggleSwitch from '@/components/common/ToggleSwitch.vue'
import { compact, hueTone } from '@/lib/adminFormat'
import { useAdminLlmStore } from '@/stores/adminLlm'
import { useToastStore } from '@/stores/toast'

/** 模型与供应方：左侧供应方列表，右侧所选供应方的连接信息与模型表（主从布局） */
const store = useAdminLlmStore()
const toast = useToastStore()
const route = useRoute()
const router = useRouter()
onMounted(() => store.load().catch((e) => toast.error(e, '加载配置失败')))

// ---------------------------------------------------------------- 选中的供应方（记在地址栏 ?p=）
const selectedId = ref<string>(typeof route.query.p === 'string' ? route.query.p : '')
watch(
  () => store.providers,
  (ps) => {
    if (!ps.find((p) => p.provider_id === selectedId.value)) selectedId.value = ps[0]?.provider_id ?? ''
  },
  { immediate: true },
)
watch(selectedId, (id) => void router.replace({ query: { ...route.query, p: id || undefined } }))
const selected = computed(() => store.providers.find((p) => p.provider_id === selectedId.value) ?? null)
const modelsOf = (id: string) => store.models.filter((m) => m.provider_id === id)
const rows = computed(() => (selected.value ? modelsOf(selected.value.provider_id) : []))

// ---------------------------------------------------------------- 供应方：添加 / 编辑 / 启停 / 删除
const pOpen = ref(false)
const pEditing = ref<ProviderOut | null>(null)
const pSaving = ref(false)
const pForm = reactive({ preset: '', provider_name: '', provider_type: 'openai_compatible', base_url: '', api_key: '', enabled: true })
const presetMap = computed(() => Object.fromEntries(store.presets.map((p) => [p.provider_type, p])))

function addProvider() {
  pEditing.value = null
  Object.assign(pForm, { preset: '', provider_name: '', provider_type: 'openai_compatible', base_url: '', api_key: '', enabled: true })
  pOpen.value = true
}
function editProvider(p: ProviderOut) {
  pEditing.value = p
  Object.assign(pForm, { preset: p.provider_type, provider_name: p.provider_name, provider_type: p.provider_type, base_url: p.base_url, api_key: '', enabled: p.enabled })
  pOpen.value = true
}
function pick(type: string) {
  const p = presetMap.value[type]
  pForm.preset = type
  if (!p) return
  pForm.provider_type = p.provider_type
  pForm.provider_name = p.provider_name
  pForm.base_url = p.base_url
}
async function saveProvider() {
  if (!pForm.provider_name.trim() || !pForm.base_url.trim()) {
    toast.push('请填写名称和接口地址', 'error')
    return
  }
  pSaving.value = true
  try {
    if (pEditing.value) {
      await api.patchProvider(pEditing.value.provider_id, {
        provider_name: pForm.provider_name.trim(),
        base_url: pForm.base_url.trim(),
        enabled: pForm.enabled,
        ...(pForm.api_key ? { api_key: pForm.api_key } : {}),
      })
    } else {
      const created = await api.createProvider({
        provider_name: pForm.provider_name.trim(),
        provider_type: pForm.provider_type,
        base_url: pForm.base_url.trim(),
        api_key: pForm.api_key || null,
        enabled: pForm.enabled,
      })
      selectedId.value = created.provider_id
    }
    pForm.api_key = ''
    pOpen.value = false
    toast.push('供应方已保存', 'success')
    await store.load(true)
  } catch (e) {
    toast.error(e)
  } finally {
    pSaving.value = false
  }
}
async function toggleProvider(p: ProviderOut, v: boolean) {
  try {
    await api.patchProvider(p.provider_id, { enabled: v })
    await store.load(true)
    toast.push(v ? '已启用' : '已停用', 'success')
  } catch (e) {
    toast.error(e)
  }
}
async function removeProvider(p: ProviderOut) {
  if (!confirm(`删除供应方「${p.provider_name}」？其下 ${modelsOf(p.provider_id).length} 个模型也将不可用。`)) return
  try {
    await api.deleteProvider(p.provider_id)
    toast.push('已删除', 'success')
    await store.load(true)
  } catch (e) {
    toast.error(e)
  }
}

// ---------------------------------------------------------------- 模型：添加 / 编辑 / 测试 / 启停 / 删除
const testing = ref<Record<string, boolean>>({})
const results = ref<Record<string, ModelTestOut>>({})
const detail = ref<ModelOut | null>(null)
const mOpen = ref(false)
const mEditing = ref<ModelOut | null>(null)
const mSaving = ref(false)
const blank = () => ({
  provider_id: selectedId.value,
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
const mForm = reactive(blank())
const exampleModels = computed(() => {
  const prov = store.providers.find((p) => p.provider_id === mForm.provider_id)
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

function addModel() {
  mEditing.value = null
  Object.assign(mForm, blank())
  mOpen.value = true
}
function editModel(m: ModelOut) {
  mEditing.value = m
  Object.assign(mForm, {
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
  mOpen.value = true
}
async function saveModel() {
  if (!mForm.provider_id || !mForm.model_name.trim()) {
    toast.push('请填写模型名', 'error')
    return
  }
  const common = {
    display_name: mForm.display_name.trim() || null,
    supports_tools: mForm.supports_tools,
    supports_forced_tool_choice: mForm.supports_forced_tool_choice,
    supports_json_schema: mForm.supports_json_schema,
    supports_json_object: mForm.supports_json_object,
    supports_vision: mForm.supports_vision,
    context_window_qty: numOrNull(mForm.context_window_qty),
    max_output_qty: numOrNull(mForm.max_output_qty),
    input_price_minor_amt: toFen(numOrNull(mForm.input_price_yuan)),
    output_price_minor_amt: toFen(numOrNull(mForm.output_price_yuan)),
    currency_code: mForm.currency_code || 'CNY',
    enabled: mForm.enabled,
  }
  mSaving.value = true
  try {
    if (mEditing.value) await api.patchModel(mEditing.value.model_profile_id, common)
    else await api.createModel({ provider_id: mForm.provider_id, model_name: mForm.model_name.trim(), ...common })
    mOpen.value = false
    toast.push('模型已保存', 'success')
    await store.load(true)
  } catch (e) {
    toast.error(e)
  } finally {
    mSaving.value = false
  }
}
async function test(m: ModelOut) {
  testing.value[m.model_profile_id] = true
  try {
    results.value[m.model_profile_id] = await api.testModel(m.model_profile_id)
    if (results.value[m.model_profile_id].adaptations?.length) await store.load(true)
    detail.value = m
  } catch (e) {
    results.value[m.model_profile_id] = { ok: false, latency_ms: null, reply: null, error: e instanceof Error ? e.message : '测试失败' }
    detail.value = m
  } finally {
    testing.value[m.model_profile_id] = false
  }
}
async function toggleModel(m: ModelOut, v: boolean) {
  try {
    await api.patchModel(m.model_profile_id, { enabled: v })
    await store.load(true)
  } catch (e) {
    toast.error(e)
  }
}
async function removeModel(m: ModelOut) {
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
const boundRoles = (id: string) => store.bindings.filter((b) => b.model_profile_id === id || b.fallback_profile_ids.includes(id))

const columns: Column[] = [
  { key: 'model', title: '模型', minWidth: 220 },
  { key: 'caps', title: '能力', minWidth: 200 },
  { key: 'context_window_qty', title: '上下文', width: 90, align: 'right', sortable: true },
  { key: 'price', title: '单价 元/百万 token（入/出）', width: 200, align: 'right' },
  { key: 'used', title: '使用中', width: 104, align: 'right' },
  { key: 'enabled', title: '启用', width: 70, align: 'center' },
  { key: 'actions', title: '', width: 196, align: 'right' },
]
</script>

<template>
  <AdminPage>
    <template #actions>
      <button class="btn-secondary" @click="addProvider"><Plus class="h-4 w-4" /> 添加供应方</button>
      <button class="btn-primary" :disabled="!selected" @click="addModel"><Plus class="h-4 w-4" /> 添加模型</button>
    </template>

    <div class="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
      <!-- 供应方列表 -->
      <aside class="ac-panel lg:sticky lg:top-20" aria-label="供应方">
        <div class="ac-panel-head">
          <span class="ac-panel-title">供应方</span>
          <span class="ac-panel-sub">{{ store.providers.length }}</span>
        </div>
        <div v-if="store.loading && !store.providers.length" class="p-4 text-[13px] text-slate-400">加载中…</div>
        <ul v-else class="p-1.5">
          <li v-for="p in store.providers" :key="p.provider_id">
            <button
              type="button"
              class="prov flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left"
              :class="p.provider_id === selectedId ? 'prov-on' : ''"
              :aria-current="p.provider_id === selectedId ? 'true' : undefined"
              @click="selectedId = p.provider_id"
            >
              <span
                class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-bold"
                :style="{ background: `var(--pastel-${hueTone(p.provider_type)})`, color: `var(--pastel-${hueTone(p.provider_type)}-ink)` }"
              >{{ p.provider_name.slice(0, 1) }}</span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-[13px] font-semibold text-white">{{ p.provider_name }}</span>
                <span class="block truncate text-[11px] text-slate-500">{{ modelsOf(p.provider_id).length }} 个模型 · {{ p.provider_type }}</span>
              </span>
              <span
                class="h-1.5 w-1.5 shrink-0 rounded-full"
                :class="!p.enabled ? 'bg-slate-500/60' : p.has_api_key ? 'bg-[var(--pastel-mint-dot)]' : 'bg-[var(--pastel-butter-dot)]'"
                :title="!p.enabled ? '已停用' : p.has_api_key ? '已启用' : '未设置 API Key'"
              />
            </button>
          </li>
          <li v-if="!store.providers.length" class="px-3 py-6 text-center text-[13px] text-slate-400">
            还没有供应方
            <button type="button" class="mt-2 block w-full text-[13px] font-semibold text-brand-300 hover:underline" @click="addProvider">添加第一个供应方</button>
          </li>
        </ul>
      </aside>

      <!-- 选中的供应方 -->
      <section v-if="selected" class="min-w-0 space-y-4">
        <div class="ac-panel">
          <div class="ac-panel-head">
            <span class="ac-panel-title">{{ selected.provider_name }}</span>
            <span class="font-mono text-[11px] text-slate-500">{{ selected.provider_type }}</span>
            <span class="flex-1" />
            <label class="flex items-center gap-2 text-[12px] text-slate-400">
              {{ selected.enabled ? '已启用' : '已停用' }}
              <ToggleSwitch small :model-value="selected.enabled" :label="`启用 ${selected.provider_name}`" @update:model-value="(v: boolean) => toggleProvider(selected!, v)" />
            </label>
            <button class="btn-secondary btn-sm" @click="editProvider(selected)"><Pencil class="h-3.5 w-3.5" /> 编辑</button>
            <button class="icon-btn hover:!text-rose-300" aria-label="删除供应方" title="删除供应方" @click="removeProvider(selected)"><Trash2 class="h-4 w-4" /></button>
          </div>
          <dl class="grid gap-x-8 gap-y-3 px-4 py-3.5 text-[13px] sm:grid-cols-3">
            <div class="min-w-0">
              <dt class="ac-caps mb-0.5">接口地址</dt>
              <dd class="truncate font-mono text-[12px] text-slate-200" :title="selected.base_url">{{ selected.base_url }}</dd>
            </div>
            <div>
              <dt class="ac-caps mb-0.5">API Key</dt>
              <dd class="flex items-center gap-1.5">
                <KeyRound class="h-3.5 w-3.5 text-slate-400" />
                <span v-if="selected.has_api_key" class="font-mono text-[12px] text-slate-200">{{ selected.api_key_mask }}</span>
                <span v-else class="text-[12px] text-amber-300">未设置</span>
              </dd>
            </div>
            <div>
              <dt class="ac-caps mb-0.5">模型</dt>
              <dd class="text-slate-200">{{ rows.length }} 个，启用 {{ rows.filter((m) => m.enabled).length }} 个</dd>
            </div>
          </dl>
        </div>

        <DataTable
          :columns="columns"
          :rows="rows"
          row-key="model_profile_id"
          :loading="store.loading"
          empty-text="这个供应方还没有模型"
          empty-desc="点右上角「添加模型」，填写模型名（或接入点 ID）与能力"
        >
          <template #cell-model="{ row }">
            <div class="min-w-0 leading-tight">
              <div class="truncate font-semibold text-white">{{ row.display_name || row.model_name }}</div>
              <div class="truncate font-mono text-[11px] text-slate-500">{{ row.model_name }}</div>
            </div>
          </template>
          <template #cell-caps="{ row }">
            <span class="flex flex-wrap gap-1">
              <span v-if="row.supports_tools" class="cap">工具</span>
              <span v-if="row.supports_tools && !row.supports_forced_tool_choice" class="cap cap-warn" title="思考模式：工具调用改为自动选择">非强制</span>
              <span v-if="row.supports_json_schema" class="cap">Schema</span>
              <span v-if="row.supports_json_object" class="cap">JSON</span>
              <span v-if="row.supports_vision" class="cap">图片</span>
            </span>
          </template>
          <template #cell-context_window_qty="{ row }"><span class="tabular-nums">{{ compact(row.context_window_qty) }}</span></template>
          <template #cell-price="{ row }">
            <span class="tabular-nums" :class="row.input_price_minor_amt == null ? 'text-amber-300' : 'text-slate-200'" :title="row.input_price_minor_amt == null ? '单价未知：调用记为待核算，不按 0 计' : ''">
              {{ yuan(row.input_price_minor_amt) }} / {{ yuan(row.output_price_minor_amt) }}
            </span>
            <span class="ml-1 text-[11px] text-slate-500">{{ row.currency_code }}</span>
          </template>
          <template #cell-used="{ row }">
            <span
              class="whitespace-nowrap tabular-nums"
              :class="boundRoles(row.model_profile_id).length ? 'text-slate-200' : 'text-slate-500'"
              :title="boundRoles(row.model_profile_id).map((b) => b.role_label).join('、') || '没有智能体使用'"
            >{{ boundRoles(row.model_profile_id).length ? `${boundRoles(row.model_profile_id).length} 个智能体` : '—' }}</span>
          </template>
          <template #cell-enabled="{ row }">
            <ToggleSwitch small :model-value="row.enabled" :label="`启用 ${row.model_name}`" @update:model-value="(v: boolean) => toggleModel(row, v)" />
          </template>
          <template #cell-actions="{ row }">
            <span class="inline-flex items-center gap-0.5 whitespace-nowrap">
              <button
                v-if="results[row.model_profile_id]"
                type="button"
                class="icon-btn"
                :title="results[row.model_profile_id].ok ? '上次测试成功，查看详情' : '上次测试失败，查看详情'"
                :aria-label="results[row.model_profile_id].ok ? '测试成功，查看详情' : '测试失败，查看详情'"
                @click="detail = row"
              >
                <CircleCheck v-if="results[row.model_profile_id].ok" class="h-4 w-4 text-emerald-300" />
                <CircleX v-else class="h-4 w-4 text-rose-300" />
              </button>
              <button class="btn-ghost btn-sm" :disabled="testing[row.model_profile_id]" title="测试连通与结构化输出" @click="test(row)">
                <Loader2 v-if="testing[row.model_profile_id]" class="h-3.5 w-3.5 animate-spin" />
                <FlaskConical v-else class="h-3.5 w-3.5" /> 测试
              </button>
              <button class="icon-btn" aria-label="编辑" title="编辑" @click="editModel(row)"><Pencil class="h-4 w-4" /></button>
              <button class="icon-btn hover:!text-rose-300" aria-label="删除" title="删除" @click="removeModel(row)"><Trash2 class="h-4 w-4" /></button>
            </span>
          </template>
        </DataTable>
        <p class="px-1 text-[12px] text-slate-500">能力决定结构化输出方式：支持工具调用优先用工具输出，否则退回 JSON 模式或提示词约束；被模型拒绝时会自动调整并记录。单价未知的调用记为“待核算”。</p>
      </section>
      <section v-else-if="!store.loading" class="ac-panel flex flex-col items-center px-6 py-16 text-center">
        <div class="text-sm font-semibold text-white">先添加一个供应方</div>
        <p class="mt-1 max-w-md text-[13px] text-slate-400">支持 OpenAI、DeepSeek、Kimi、火山方舟、通义千问、智谱，以及任何 OpenAI 兼容接口。</p>
        <button class="btn-primary mt-4" @click="addProvider"><Plus class="h-4 w-4" /> 添加供应方</button>
      </section>
    </div>

    <!-- 供应方表单 -->
    <SideDrawer v-model="pOpen" :title="pEditing ? `编辑供应方：${pEditing.provider_name}` : '添加供应方'" desc="OpenAI 兼容接口地址与密钥；密钥加密保存，页面只显示掩码">
      <form id="provider-form" class="space-y-4" @submit.prevent="saveProvider">
        <div v-if="!pEditing">
          <div class="label">选择预设</div>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="p in store.presets"
              :key="p.provider_type"
              type="button"
              class="rounded-lg border px-3 py-2 text-left text-[13px] transition"
              :class="pForm.preset === p.provider_type ? 'border-[var(--cs-ink)] bg-[var(--cs-surface-sunken)]' : 'hairline hover:border-slate-400'"
              @click="pick(p.provider_type)"
            >
              <span class="block font-semibold text-white">{{ p.provider_name }}</span>
              <span class="block truncate font-mono text-[11px] text-slate-500">{{ p.base_url || '自定义地址' }}</span>
            </button>
          </div>
          <p v-if="presetMap[pForm.preset]?.note" class="mt-2 text-xs text-slate-500">{{ presetMap[pForm.preset]?.note }}</p>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="pn">显示名称</label>
            <input id="pn" v-model="pForm.provider_name" class="input" required />
          </div>
          <div>
            <label class="label" for="pt">类型</label>
            <input id="pt" v-model="pForm.provider_type" class="input font-mono" :disabled="!!pEditing" />
          </div>
        </div>
        <div>
          <label class="label" for="pu">接口地址（base_url）</label>
          <input id="pu" v-model="pForm.base_url" class="input font-mono" placeholder="https://api.example.com/v1" required />
        </div>
        <div>
          <label class="label" for="pk">API Key{{ pEditing ? '（留空则不修改）' : '' }}</label>
          <input
            id="pk"
            v-model="pForm.api_key"
            type="password"
            class="input font-mono"
            autocomplete="new-password"
            :placeholder="pEditing?.has_api_key ? `当前：${pEditing.api_key_mask}` : 'sk-…'"
          />
        </div>
        <label class="flex items-center justify-between rounded-lg sunken px-3.5 py-2.5 text-[13px]">
          <span class="font-semibold text-white">启用该供应方</span>
          <ToggleSwitch v-model="pForm.enabled" label="启用" />
        </label>
      </form>
      <template #footer>
        <button type="button" class="btn-ghost" @click="pOpen = false">取消</button>
        <button type="submit" form="provider-form" class="btn-primary" :disabled="pSaving">保存</button>
      </template>
    </SideDrawer>

    <!-- 测试结果 -->
    <SideDrawer
      :model-value="!!detail"
      :title="detail ? `测试结果：${detail.display_name || detail.model_name}` : ''"
      :width="480"
      @update:model-value="(v: boolean) => !v && (detail = null)"
    >
      <template v-if="detail && results[detail.model_profile_id]">
        <div class="rounded-lg border p-3.5 text-[13px]" :class="results[detail.model_profile_id].ok ? 'border-emerald-300/40' : 'border-rose-300/40'">
          <template v-if="results[detail.model_profile_id].ok">
            <div class="flex items-center gap-2 font-semibold text-white"><CircleCheck class="h-4 w-4 text-emerald-300" /> 连通成功 · 结构化输出可用</div>
            <div class="mt-1 text-slate-400">耗时 {{ results[detail.model_profile_id].latency_ms }} ms</div>
          </template>
          <template v-else>
            <div class="flex items-center gap-2 font-semibold text-white">
              <CircleX class="h-4 w-4 text-rose-300" />
              {{ results[detail.model_profile_id].reply ? `连通成功（${results[detail.model_profile_id].latency_ms} ms），但结构化输出失败` : '测试失败' }}
            </div>
          </template>
        </div>
        <div v-if="results[detail.model_profile_id].error" class="mt-4">
          <div class="label">错误信息</div>
          <code class="ac-code">{{ results[detail.model_profile_id].error }}</code>
        </div>
        <div v-if="results[detail.model_profile_id].reply" class="mt-4">
          <div class="label">模型回复</div>
          <div class="rounded-lg sunken p-3 text-[13px] whitespace-pre-wrap">{{ results[detail.model_profile_id].reply }}</div>
        </div>
        <div v-if="results[detail.model_profile_id].adaptations?.length" class="mt-4">
          <div class="label">已自动调整的能力配置</div>
          <ul class="space-y-1.5 text-[13px]">
            <li v-for="a in results[detail.model_profile_id].adaptations" :key="a" class="rounded-lg border border-amber-300/40 px-3 py-2 text-slate-200">{{ a }}</li>
          </ul>
        </div>
      </template>
    </SideDrawer>

    <!-- 模型表单 -->
    <SideDrawer v-model="mOpen" :title="mEditing ? `编辑模型：${mEditing.display_name || mEditing.model_name}` : `添加模型 · ${selected?.provider_name ?? ''}`" :width="600">
      <form id="model-form" class="space-y-5" @submit.prevent="saveModel">
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <label class="label" for="mn">模型名 / 接入点 ID</label>
            <input id="mn" v-model="mForm.model_name" class="input font-mono" list="cs-model-examples" :disabled="!!mEditing" required />
            <datalist id="cs-model-examples">
              <option v-for="x in exampleModels" :key="x" :value="x" />
            </datalist>
            <div v-if="exampleModels.length && !mEditing" class="mt-2 flex flex-wrap gap-1.5">
              <button v-for="x in exampleModels" :key="x" type="button" class="chip !px-2 !py-0.5 !text-[11px] font-mono" @click="mForm.model_name = x">{{ x }}</button>
            </div>
          </div>
          <div>
            <label class="label" for="md">显示名称</label>
            <input id="md" v-model="mForm.display_name" class="input" placeholder="可选" />
          </div>
          <div>
            <label class="label" for="mp">供应方</label>
            <select id="mp" v-model="mForm.provider_id" class="input" :disabled="!!mEditing">
              <option v-for="p in store.providers" :key="p.provider_id" :value="p.provider_id">{{ p.provider_name }}</option>
            </select>
          </div>
        </div>
        <fieldset>
          <legend class="label">能力</legend>
          <div class="divide-y overflow-hidden rounded-lg border border-[var(--cs-line)] [&>*]:border-[var(--cs-line)]">
            <label v-for="c in CAPS" :key="c.key" class="flex items-center gap-3 px-3.5 py-2.5">
              <span class="min-w-0 flex-1">
                <span class="block text-[13px] font-semibold text-white">{{ c.label }}</span>
                <span class="block text-xs text-slate-500">{{ c.help }}</span>
              </span>
              <ToggleSwitch
                v-model="mForm[c.key]"
                small
                :label="c.label"
                :disabled="c.key === 'supports_forced_tool_choice' && !mForm.supports_tools"
              />
            </label>
          </div>
        </fieldset>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="mc">上下文长度</label>
            <input id="mc" v-model.number="mForm.context_window_qty" type="number" min="0" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mo">最大输出 token</label>
            <input id="mo" v-model.number="mForm.max_output_qty" type="number" min="0" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mi">输入价（元/百万 token）</label>
            <input id="mi" v-model.number="mForm.input_price_yuan" type="number" min="0" step="0.01" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mout">输出价（元/百万 token）</label>
            <input id="mout" v-model.number="mForm.output_price_yuan" type="number" min="0" step="0.01" class="input" placeholder="未知" />
          </div>
          <div>
            <label class="label" for="mcur">币种</label>
            <input id="mcur" v-model="mForm.currency_code" class="input" maxlength="8" />
          </div>
          <label class="flex items-end justify-between gap-3 pb-2 text-[13px]">
            <span class="font-semibold text-white">启用</span>
            <ToggleSwitch v-model="mForm.enabled" label="启用" />
          </label>
        </div>
        <p class="text-xs text-slate-500">单价未知的调用记为“待核算”，不按 0 计入费用。</p>
      </form>
      <template #footer>
        <button type="button" class="btn-ghost" @click="mOpen = false">取消</button>
        <button type="submit" form="model-form" class="btn-primary" :disabled="mSaving">保存</button>
      </template>
    </SideDrawer>
  </AdminPage>
</template>

<style scoped>
.prov:hover {
  background: var(--cs-line);
}
.prov-on {
  background: var(--cs-surface-sunken) !important;
  box-shadow: inset 0 0 0 1px var(--cs-line-strong);
}
.cap {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--cs-line-strong);
  border-radius: 6px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 18px;
  color: var(--color-slate-300);
}
.cap-warn {
  border-color: color-mix(in srgb, var(--pastel-butter-dot) 60%, transparent);
  color: var(--color-amber-300);
}
</style>
