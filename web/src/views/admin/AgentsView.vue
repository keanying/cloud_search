<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Info } from 'lucide-vue-next'
import type { AgentBindingOut, ModelOut } from '@/api/types'
import { api } from '@/api/client'
import AdminPage from '@/components/admin/AdminPage.vue'
import FallbackPicker from '@/components/admin/FallbackPicker.vue'
import SaveBar from '@/components/admin/SaveBar.vue'
import DataTable, { type Column } from '@/components/common/DataTable.vue'
import { useDirtyGuard } from '@/lib/useDirtyGuard'
import { useAdminLlmStore } from '@/stores/adminLlm'
import { useToastStore } from '@/stores/toast'

/** 智能体分工：行内编辑；所有修改通过底部同一个保存条提交（与运行参数一致） */
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
const saving = ref(false)

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
const dirtyCount = computed(() => dirtyRoles.value.length)
useDirtyGuard(dirtyCount)

async function saveRole(role: string): Promise<boolean> {
  const d = drafts[role]
  if (!d.model_profile_id) {
    if (role === 'default') {
      toast.push('默认模型必须选择一个模型', 'error')
      return false
    }
    await api.deleteAgentBinding(role) // 改用默认模型
    return true
  }
  await api.putAgentBinding(role, {
    model_profile_id: d.model_profile_id,
    fallback_profile_ids: d.fallback_profile_ids.filter((x) => x !== d.model_profile_id),
    temperature: norm(d.temperature),
    max_tokens: norm(d.max_tokens),
  })
  return true
}
async function saveAll() {
  saving.value = true
  let ok = 0
  const failed: string[] = []
  for (const r of dirtyRoles.value) {
    try {
      if (await saveRole(r)) ok++
      else failed.push(r)
    } catch (e) {
      failed.push(r)
      toast.error(e, `保存「${store.bindings.find((b) => b.agent_role === r)?.role_label ?? r}」失败`)
    }
  }
  saving.value = false
  if (ok) toast.push(`已保存 ${ok} 个智能体，新任务立即生效`, 'success')
  // 只刷新服务端数据；保存失败的行保留草稿
  const keep = Object.fromEntries(failed.map((r) => [r, drafts[r]]))
  await store.load(true)
  Object.assign(drafts, keep)
}
function discard() {
  for (const b of store.bindings) drafts[b.agent_role] = snapshot(b)
}

const ROLE_HINT: Record<string, string> = {
  requirement_compiler: '强推理',
  coordinator: '强推理',
  verifier: '强推理',
  analyst: '强推理',
  search_planner: '快速低价',
  extractor: '快速低价',
  browser_researcher: '快速低价',
  report_writer: '长上下文',
}
const grouped = computed(() => {
  const map = new Map<string, ModelOut[]>()
  for (const m of store.enabledModels) {
    const k = m.provider_name ?? '其他'
    map.set(k, [...(map.get(k) ?? []), m])
  }
  return [...map.entries()]
})
const defaultModel = computed(() => {
  const d = store.bindings.find((b) => b.agent_role === 'default')
  return d?.model_profile_id ? store.modelLabel(d.model_profile_id) : null
})

const columns: Column[] = [
  { key: 'role', title: '智能体', width: 280, fixed: 'left' },
  { key: 'model_profile_id', title: '主模型', minWidth: 200 },
  { key: 'fallbacks', title: '备用模型（按顺序）', minWidth: 180 },
  { key: 'temperature', title: '温度', width: 100 },
  { key: 'max_tokens', title: '最大输出', width: 104 },
  { key: 'state', title: '', width: 76, align: 'right' },
]
</script>

<template>
  <AdminPage>
    <template #actions>
      <RouterLink :to="{ name: 'admin-models' }" class="btn-secondary">管理模型（{{ store.enabledModels.length }} 个可用）</RouterLink>
    </template>

    <div class="ac-panel mb-4 flex gap-2.5 px-4 py-3 text-[13px] leading-6 text-slate-300">
      <Info class="mt-1 h-4 w-4 shrink-0 text-slate-400" />
      <p>
        理解、协调、核验与分析建议用强推理模型；搜索规划与信息抽取调用最频繁，可用快速低价模型；报告写作建议用长上下文模型。
        未单独指定的智能体使用「默认模型」<template v-if="defaultModel">（当前：{{ defaultModel }}）</template>；主模型失败时按顺序尝试备用模型。
      </p>
    </div>

    <DataTable :columns="columns" :rows="store.bindings" row-key="agent_role" :loading="store.loading" empty-text="暂无智能体">
      <template #cell-role="{ row }">
        <div class="min-w-0 leading-tight">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-white">{{ row.role_label }}</span>
            <span v-if="ROLE_HINT[row.agent_role]" class="hint" title="建议的模型类型">{{ ROLE_HINT[row.agent_role] }}</span>
            <span class="truncate font-mono text-[11px] text-slate-500">{{ row.agent_role }}</span>
          </div>
          <div class="mt-1 truncate text-[12px] text-slate-400" :title="row.description">{{ row.description }}</div>
        </div>
      </template>
      <template #cell-model_profile_id="{ row }">
        <select
          v-if="drafts[row.agent_role]"
          v-model="drafts[row.agent_role].model_profile_id"
          class="input"
          :class="!drafts[row.agent_role].model_profile_id && row.agent_role !== 'default' ? 'text-slate-400' : ''"
          :aria-label="`${row.role_label} 主模型`"
        >
          <option value="">{{ row.agent_role === 'default' ? '— 选择模型 —' : '使用默认模型' }}</option>
          <optgroup v-for="[prov, ms] in grouped" :key="prov" :label="prov">
            <option v-for="m in ms" :key="m.model_profile_id" :value="m.model_profile_id">{{ m.display_name || m.model_name }}</option>
          </optgroup>
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
          class="input tabular-nums"
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
          class="input tabular-nums"
          placeholder="默认"
          :aria-label="`${row.role_label} 最大输出 token`"
        />
      </template>
      <template #cell-state="{ row }">
        <span v-if="isDirty(row)" class="inline-flex items-center gap-1 text-[12px] font-medium text-amber-300">
          <span class="h-1.5 w-1.5 rounded-full bg-[var(--pastel-butter-dot)]" /> 已修改
        </span>
        <span v-else-if="!row.model_profile_id" class="text-[12px] text-slate-500">{{ row.agent_role === 'default' ? '未设置' : '用默认' }}</span>
      </template>
    </DataTable>

    <SaveBar :count="dirtyCount" :saving="saving" @save="saveAll" @discard="discard" />
  </AdminPage>
</template>

<style scoped>
.hint {
  display: inline-flex;
  border: 1px solid var(--cs-line-strong);
  border-radius: 6px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 18px;
  color: var(--color-slate-300);
  white-space: nowrap;
}
</style>
