<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Lightbulb, Loader2, Save } from 'lucide-vue-next'
import type { AgentBindingOut } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import FallbackPicker from '@/components/admin/FallbackPicker.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import { useAdminLlmStore } from '@/stores/adminLlm'
import { useToastStore } from '@/stores/toast'

const store = useAdminLlmStore()
const toast = useToastStore()
onMounted(() => store.load().catch((e) => toast.error(e, '加载配置失败')))

interface Draft {
  model_profile_id: string
  fallback_profile_ids: string[]
  temperature: number | null | ''
  max_tokens: number | null | ''
}
const drafts = reactive<Record<string, Draft>>({})
const saving = ref<Record<string, boolean>>({})
const savingAll = ref(false)

function snapshot(b: AgentBindingOut): Draft {
  return {
    model_profile_id: b.model_profile_id ?? '',
    fallback_profile_ids: [...b.fallback_profile_ids],
    temperature: b.temperature,
    max_tokens: b.max_tokens,
  }
}
watch(
  () => store.bindings,
  (bs) => {
    for (const b of bs) drafts[b.agent_role] = snapshot(b)
  },
  { immediate: true },
)

const norm = (v: number | null | '') => (v === '' || v == null || Number.isNaN(v) ? null : Number(v))
function isDirty(b: AgentBindingOut): boolean {
  const d = drafts[b.agent_role]
  if (!d) return false
  const o = snapshot(b)
  return (
    d.model_profile_id !== o.model_profile_id ||
    norm(d.temperature) !== norm(o.temperature) ||
    norm(d.max_tokens) !== norm(o.max_tokens) ||
    d.fallback_profile_ids.filter((x) => x !== d.model_profile_id).join() !== o.fallback_profile_ids.join()
  )
}
const dirtyRoles = computed(() => store.bindings.filter(isDirty).map((b) => b.agent_role))

async function saveRole(role: string, quiet = false): Promise<boolean> {
  const d = drafts[role]
  if (!d.model_profile_id) {
    if (!quiet) toast.push('请选择主模型', 'error')
    return false
  }
  saving.value[role] = true
  try {
    await api.putAgentBinding(role, {
      model_profile_id: d.model_profile_id,
      fallback_profile_ids: d.fallback_profile_ids.filter((x) => x !== d.model_profile_id),
      temperature: norm(d.temperature),
      max_tokens: norm(d.max_tokens),
    })
    return true
  } catch (e) {
    toast.error(e, `保存「${role}」失败`)
    return false
  } finally {
    saving.value[role] = false
  }
}
async function save(role: string) {
  if (await saveRole(role)) {
    toast.push('已保存', 'success')
    await store.load(true)
  }
}
async function saveAll() {
  savingAll.value = true
  let ok = 0
  for (const r of dirtyRoles.value) if (await saveRole(r, true)) ok++
  savingAll.value = false
  if (ok) toast.push(`已保存 ${ok} 个智能体`, 'success')
  await store.load(true)
}

const ROLE_HINT: Record<string, string> = {
  requirement_compiler: '强推理',
  coordinator: '强推理',
  verifier: '强推理',
  search_planner: '快速低价',
  extractor: '快速低价',
  browser_researcher: '快速低价',
  analyst: '强推理',
  report_writer: '长上下文',
}

const columns: Column[] = [
  { key: 'role', title: '智能体', width: 300, fixed: 'left' },
  { key: 'model_profile_id', title: '主模型', minWidth: 260 },
  { key: 'fallbacks', title: '备用模型', minWidth: 240 },
  { key: 'temperature', title: '温度', width: 110 },
  { key: 'max_tokens', title: '最大输出', width: 130 },
  { key: 'actions', title: '', width: 150, align: 'right', fixed: 'right' },
]
</script>

<template>
  <AdminPage>
    <template #actions>
      <span v-if="dirtyRoles.length" class="text-sm text-amber-300">{{ dirtyRoles.length }} 项未保存</span>
      <button class="btn-primary" :disabled="!dirtyRoles.length || savingAll" @click="saveAll">
        <Loader2 v-if="savingAll" class="h-4 w-4 animate-spin" /><Save v-else class="h-4 w-4" /> 保存全部
      </button>
    </template>

    <div class="mb-5 grid gap-3 lg:grid-cols-3">
      <div class="card-lilac flex gap-3 p-5 lg:col-span-2">
        <Lightbulb class="mt-0.5 h-5 w-5 shrink-0 accent-ink" />
        <p class="text-sm leading-6 accent-ink">
          八个智能体各司其职，可绑定不同模型：<b>理解、协调与核验</b>建议用强推理模型；<b>搜索规划与信息抽取</b>调用最频繁，可用快速低价模型；<b>报告写作</b>建议用长上下文模型。未绑定的角色使用“默认模型”。主模型失败时按顺序尝试备用模型。
        </p>
      </div>
      <div class="card-butter flex items-center gap-4 p-5">
        <div class="min-w-0 flex-1">
          <div class="text-[28px] leading-8 font-bold tabular-nums accent-ink">{{ store.enabledModels.length }}</div>
          <div class="text-sm accent-ink opacity-80">个可用模型</div>
        </div>
        <RouterLink :to="{ name: 'admin-models' }" class="btn-secondary btn-sm">管理模型</RouterLink>
      </div>
    </div>

    <DataTable :columns="columns" :rows="store.bindings" row-key="agent_role" :loading="store.loading" empty-text="暂无智能体">
      <template #cell-role="{ row }">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-white">{{ row.role_label }}</span>
            <span v-if="ROLE_HINT[row.agent_role]" class="pill sunken text-[11px] text-slate-400">建议{{ ROLE_HINT[row.agent_role] }}</span>
          </div>
          <div class="font-mono text-[11px] text-slate-500">{{ row.agent_role }}</div>
          <div class="mt-0.5 line-clamp-2 text-xs leading-5 text-slate-400" :title="row.description">{{ row.description }}</div>
        </div>
      </template>
      <template #cell-model_profile_id="{ row }">
        <select v-if="drafts[row.agent_role]" v-model="drafts[row.agent_role].model_profile_id" class="input !py-2" :aria-label="`${row.role_label} 主模型`">
          <option value="">{{ row.agent_role === 'default' ? '— 选择模型 —' : '使用默认模型' }}</option>
          <option v-for="m in store.enabledModels" :key="m.model_profile_id" :value="m.model_profile_id">
            {{ m.provider_name }} · {{ m.display_name || m.model_name }}
          </option>
        </select>
      </template>
      <template #cell-fallbacks="{ row }">
        <FallbackPicker
          v-if="drafts[row.agent_role]"
          v-model="drafts[row.agent_role].fallback_profile_ids"
          :models="store.enabledModels"
          :exclude="drafts[row.agent_role].model_profile_id"
          :label="`${row.role_label} 备用模型`"
        />
      </template>
      <template #cell-temperature="{ row }">
        <input
          v-if="drafts[row.agent_role]"
          v-model.number="drafts[row.agent_role].temperature"
          type="number"
          min="0"
          max="2"
          step="0.1"
          class="input !py-2"
          placeholder="默认"
          :aria-label="`${row.role_label} 温度`"
        />
      </template>
      <template #cell-max_tokens="{ row }">
        <input
          v-if="drafts[row.agent_role]"
          v-model.number="drafts[row.agent_role].max_tokens"
          type="number"
          min="1"
          class="input !py-2"
          placeholder="默认"
          :aria-label="`${row.role_label} 最大输出 token`"
        />
      </template>
      <template #cell-actions="{ row }">
        <span class="inline-flex items-center gap-2">
          <StatusPill v-if="isDirty(row)" tone="butter" text="未保存" />
          <StatusPill v-else-if="!row.model_profile_id" tone="gray" :text="row.agent_role === 'default' ? '未设置' : '用默认'" />
          <button class="btn-primary btn-sm" :disabled="!isDirty(row) || saving[row.agent_role]" @click="save(row.agent_role)">
            <Loader2 v-if="saving[row.agent_role]" class="h-3.5 w-3.5 animate-spin" /> 保存
          </button>
        </span>
      </template>
    </DataTable>
  </AdminPage>
</template>
