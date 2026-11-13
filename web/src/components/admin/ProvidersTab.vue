<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { KeyRound, Pencil, Plus, Trash2, X } from 'lucide-vue-next'
import type { ProviderOut, ProviderPreset } from '@/api/types'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toast'
import EmptyState from '@/components/common/EmptyState.vue'

const props = defineProps<{ providers: ProviderOut[]; presets: ProviderPreset[] }>()
const emit = defineEmits<{ changed: [] }>()
const toast = useToastStore()

const formOpen = ref(false)
const editing = ref<ProviderOut | null>(null)
const saving = ref(false)
const form = reactive({ preset: '', provider_name: '', provider_type: 'openai_compatible', base_url: '', api_key: '', enabled: true })

const presetMap = computed(() => Object.fromEntries(props.presets.map((p) => [p.provider_type, p])))

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
function applyPreset() {
  const p = presetMap.value[form.preset]
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
    emit('changed')
  } catch (e) {
    toast.error(e)
  } finally {
    saving.value = false
  }
}

async function toggle(p: ProviderOut) {
  try {
    await api.patchProvider(p.provider_id, { enabled: !p.enabled })
    emit('changed')
  } catch (e) {
    toast.error(e)
  }
}

async function remove(p: ProviderOut) {
  if (!confirm(`删除供应方「${p.provider_name}」？其下模型也将不可用。`)) return
  try {
    await api.deleteProvider(p.provider_id)
    emit('changed')
  } catch (e) {
    toast.error(e)
  }
}
</script>

<template>
  <div>
    <div class="mb-3 flex items-center justify-between">
      <p class="text-sm text-slate-400">所有供应方均通过 OpenAI 兼容接口接入。API Key 只写入后端加密保存，页面仅显示掩码。</p>
      <button class="btn-primary btn-sm shrink-0" @click="openAdd"><Plus class="h-3.5 w-3.5" /> 添加供应方</button>
    </div>

    <form v-if="formOpen" class="glass mb-4 space-y-3 p-6" @submit.prevent="save">
      <div class="flex items-center justify-between">
        <h3 class="card-title">{{ editing ? `编辑：${editing.provider_name}` : '添加供应方' }}</h3>
        <button type="button" class="icon-btn" aria-label="取消" @click="formOpen = false"><X class="h-4 w-4" /></button>
      </div>
      <div v-if="!editing">
        <label class="label" for="pp">预设</label>
        <select id="pp" v-model="form.preset" class="input" @change="applyPreset">
          <option value="">— 选择预设（OpenAI / DeepSeek / Kimi / 火山方舟 / 通义千问 / 智谱 / 自定义）—</option>
          <option v-for="p in presets" :key="p.provider_type" :value="p.provider_type">{{ p.provider_name }}</option>
        </select>
        <p v-if="presetMap[form.preset]?.note" class="mt-1 text-xs text-slate-500">{{ presetMap[form.preset]?.note }}</p>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        <div>
          <label class="label" for="pn">显示名称</label>
          <input id="pn" v-model="form.provider_name" class="input" required />
        </div>
        <div>
          <label class="label" for="pt">类型</label>
          <input id="pt" v-model="form.provider_type" class="input" :disabled="!!editing" />
        </div>
        <div class="md:col-span-2">
          <label class="label" for="pu">接口地址（base_url）</label>
          <input id="pu" v-model="form.base_url" class="input font-mono" placeholder="https://api.example.com/v1" required />
        </div>
        <div class="md:col-span-2">
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
      </div>
      <label class="flex items-center gap-2 text-sm"><input v-model="form.enabled" type="checkbox" class="accent-blue-500" /> 启用</label>
      <div class="flex gap-2">
        <button type="submit" class="btn-primary btn-sm" :disabled="saving">保存</button>
        <button type="button" class="btn-ghost btn-sm" @click="formOpen = false">取消</button>
      </div>
    </form>

    <EmptyState v-if="!providers.length" class="glass" title="还没有配置供应方" desc="添加至少一个供应方和模型后，智能体才能调用大模型" />
    <ul class="space-y-2">
      <li v-for="p in providers" :key="p.provider_id" class="glass flex flex-wrap items-center gap-3 p-5">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-white">{{ p.provider_name }}</span>
            <span class="pill sunken font-mono text-slate-400">{{ p.provider_type }}</span>
            <span v-if="!p.enabled" class="text-xs text-amber-300">已停用</span>
          </div>
          <div class="mt-0.5 truncate font-mono text-xs text-slate-500">{{ p.base_url }}</div>
          <div class="mt-0.5 flex items-center gap-1 text-xs" :class="p.has_api_key ? 'text-slate-400' : 'text-amber-300'">
            <KeyRound class="h-3 w-3" /> {{ p.has_api_key ? p.api_key_mask : '未设置 API Key' }}
          </div>
        </div>
        <label class="flex items-center gap-1.5 text-xs text-slate-300">
          <input type="checkbox" :checked="p.enabled" class="accent-blue-500" @change="toggle(p)" /> 启用
        </label>
        <button class="icon-btn" aria-label="编辑" @click="openEdit(p)"><Pencil class="h-4 w-4" /></button>
        <button class="icon-btn" aria-label="删除" @click="remove(p)"><Trash2 class="h-4 w-4" /></button>
      </li>
    </ul>
  </div>
</template>
