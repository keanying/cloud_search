<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { KeyRound, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import type { ProviderOut } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import SideDrawer from '@/components/common/SideDrawer.vue'
import ToggleSwitch from '@/components/common/ToggleSwitch.vue'
import { hueTone } from '@/lib/adminFormat'
import { useAdminLlmStore } from '@/stores/adminLlm'
import { useToastStore } from '@/stores/toast'

const store = useAdminLlmStore()
const toast = useToastStore()
onMounted(() => store.load().catch((e) => toast.error(e, '加载配置失败')))

const formOpen = ref(false)
const editing = ref<ProviderOut | null>(null)
const saving = ref(false)
const form = reactive({ preset: '', provider_name: '', provider_type: 'openai_compatible', base_url: '', api_key: '', enabled: true })
const presetMap = computed(() => Object.fromEntries(store.presets.map((p) => [p.provider_type, p])))
const modelCount = (id: string) => store.models.filter((m) => m.provider_id === id).length

const columns: Column[] = [
  { key: 'provider_name', title: '供应方', minWidth: 220, width: 260 },
  { key: 'base_url', title: '接口地址', minWidth: 280 },
  { key: 'api_key', title: 'API Key', width: 200 },
  { key: 'models', title: '模型', width: 90, align: 'right' },
  { key: 'enabled', title: '启用', width: 90, align: 'center' },
  { key: 'actions', title: '', width: 110, align: 'right', fixed: 'right' },
]

function openAdd() {
  editing.value = null
  Object.assign(form, { preset: '', provider_name: '', provider_type: 'openai_compatible', base_url: '', api_key: '', enabled: true })
  formOpen.value = true
}
function openEdit(p: ProviderOut) {
  editing.value = p
  Object.assign(form, { preset: p.provider_type, provider_name: p.provider_name, provider_type: p.provider_type, base_url: p.base_url, api_key: '', enabled: p.enabled })
  formOpen.value = true
}
function pick(type: string) {
  const p = presetMap.value[type]
  form.preset = type
  if (!p) return
  form.provider_type = p.provider_type
  form.provider_name = p.provider_name
  form.base_url = p.base_url
}

async function save() {
  if (!form.provider_name.trim() || !form.base_url.trim()) {
    toast.push('请填写名称和接口地址', 'error')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await api.patchProvider(editing.value.provider_id, {
        provider_name: form.provider_name.trim(),
        base_url: form.base_url.trim(),
        enabled: form.enabled,
        ...(form.api_key ? { api_key: form.api_key } : {}),
      })
    } else {
      await api.createProvider({
        provider_name: form.provider_name.trim(),
        provider_type: form.provider_type,
        base_url: form.base_url.trim(),
        api_key: form.api_key || null,
        enabled: form.enabled,
      })
    }
    form.api_key = ''
    formOpen.value = false
    toast.push('已保存', 'success')
    await store.load(true)
  } catch (e) {
    toast.error(e)
  } finally {
    saving.value = false
  }
}

async function toggle(p: ProviderOut, v: boolean) {
  try {
    await api.patchProvider(p.provider_id, { enabled: v })
    await store.load(true)
  } catch (e) {
    toast.error(e)
  }
}
async function remove(p: ProviderOut) {
  if (!confirm(`删除供应方「${p.provider_name}」？其下 ${modelCount(p.provider_id)} 个模型也将不可用。`)) return
  try {
    await api.deleteProvider(p.provider_id)
    toast.push('已删除', 'success')
    await store.load(true)
  } catch (e) {
    toast.error(e)
  }
}
</script>

<template>
  <AdminPage>
    <template #actions>
      <button class="btn-primary" @click="openAdd"><Plus class="h-4 w-4" /> 添加供应方</button>
    </template>

    <div class="mb-4 flex flex-wrap items-center gap-3 rounded-2xl card-sky px-5 py-3.5 text-sm accent-ink">
      <KeyRound class="h-4 w-4 shrink-0" />
      <span class="min-w-0 flex-1">所有供应方均通过 OpenAI 兼容接口接入。API Key 在后端加密保存，页面只显示掩码；编辑时留空表示不修改。</span>
    </div>

    <DataTable
      :columns="columns"
      :rows="store.providers"
      row-key="provider_id"
      :loading="store.loading"
      empty-text="还没有配置供应方"
      empty-desc="添加至少一个供应方和模型后，智能体才能调用大模型"
    >
      <template #cell-provider_name="{ row }">
        <span class="flex items-center gap-3">
          <span
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl text-sm font-bold"
            :style="{ background: `var(--pastel-${hueTone(row.provider_type)})`, color: `var(--pastel-${hueTone(row.provider_type)}-ink)` }"
          >{{ row.provider_name.slice(0, 1) }}</span>
          <span class="min-w-0 leading-tight">
            <span class="block truncate font-semibold text-white">{{ row.provider_name }}</span>
            <span class="block font-mono text-[11px] text-slate-500">{{ row.provider_type }}</span>
          </span>
        </span>
      </template>
      <template #cell-base_url="{ row }"><span class="block truncate font-mono text-xs text-slate-300" :title="row.base_url">{{ row.base_url }}</span></template>
      <template #cell-api_key="{ row }">
        <span v-if="row.has_api_key" class="font-mono text-xs text-slate-300">{{ row.api_key_mask }}</span>
        <span v-else class="pill card-butter accent-ink">未设置</span>
      </template>
      <template #cell-models="{ row }"><span class="tabular-nums">{{ modelCount(row.provider_id) }}</span></template>
      <template #cell-enabled="{ row }">
        <ToggleSwitch small :model-value="row.enabled" :label="`启用 ${row.provider_name}`" @update:model-value="(v: boolean) => toggle(row, v)" />
      </template>
      <template #cell-actions="{ row }">
        <span class="inline-flex gap-0.5">
          <button class="icon-btn !h-8 !w-8" aria-label="编辑" title="编辑" @click="openEdit(row)"><Pencil class="h-4 w-4" /></button>
          <button class="icon-btn !h-8 !w-8 hover:!text-rose-300" aria-label="删除" title="删除" @click="remove(row)"><Trash2 class="h-4 w-4" /></button>
        </span>
      </template>
    </DataTable>

    <SideDrawer v-model="formOpen" :title="editing ? `编辑供应方：${editing.provider_name}` : '添加供应方'" desc="填写 OpenAI 兼容接口地址与密钥">
      <form id="provider-form" class="space-y-4" @submit.prevent="save">
        <div v-if="!editing">
          <div class="label">选择预设</div>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="p in store.presets"
              :key="p.provider_type"
              type="button"
              class="rounded-2xl border px-3 py-2.5 text-left text-sm transition"
              :class="form.preset === p.provider_type ? 'border-[var(--cs-ink)] bg-[var(--cs-surface-sunken)]' : 'hairline hover:border-slate-400'"
              @click="pick(p.provider_type)"
            >
              <span class="block font-semibold text-white">{{ p.provider_name }}</span>
              <span class="block truncate font-mono text-[11px] text-slate-500">{{ p.base_url || '自定义地址' }}</span>
            </button>
          </div>
          <p v-if="presetMap[form.preset]?.note" class="mt-2 text-xs text-slate-500">{{ presetMap[form.preset]?.note }}</p>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="pn">显示名称</label>
            <input id="pn" v-model="form.provider_name" class="input" required />
          </div>
          <div>
            <label class="label" for="pt">类型</label>
            <input id="pt" v-model="form.provider_type" class="input font-mono" :disabled="!!editing" />
          </div>
        </div>
        <div>
          <label class="label" for="pu">接口地址（base_url）</label>
          <input id="pu" v-model="form.base_url" class="input font-mono" placeholder="https://api.example.com/v1" required />
        </div>
        <div>
          <label class="label" for="pk">API Key{{ editing ? '（留空则不修改）' : '' }}</label>
          <input
            id="pk"
            v-model="form.api_key"
            type="password"
            class="input font-mono"
            autocomplete="new-password"
            :placeholder="editing?.has_api_key ? `当前：${editing.api_key_mask}` : 'sk-…'"
          />
        </div>
        <label class="flex items-center justify-between rounded-2xl sunken px-4 py-3 text-sm">
          <span class="font-semibold text-white">启用该供应方</span>
          <ToggleSwitch v-model="form.enabled" label="启用" />
        </label>
      </form>
      <template #footer>
        <button type="button" class="btn-ghost" @click="formOpen = false">取消</button>
        <button type="submit" form="provider-form" class="btn-primary" :disabled="saving">保存</button>
      </template>
    </SideDrawer>
  </AdminPage>
</template>
