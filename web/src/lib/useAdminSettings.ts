import { computed, onMounted, reactive, ref } from 'vue'
import type { AdminSettings, SettingField, SettingValue } from '@/api/types'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toast'

/** 运行参数（覆盖 config.yaml）：加载、草稿、是否修改、保存与恢复默认 */
export function useAdminSettings(groups: SettingField['group'][]) {
  const toast = useToastStore()
  const data = ref<AdminSettings | null>(null)
  const drafts = reactive<Record<string, SettingValue>>({})
  const loading = ref(true)
  const saving = ref(false)

  const fields = computed(() => (data.value?.fields ?? []).filter((f) => groups.includes(f.group)))
  const same = (a: SettingValue, b: SettingValue) => JSON.stringify(a) === JSON.stringify(b)
  const dirtyKeys = computed(() => fields.value.filter((f) => !same(drafts[f.key], f.value)).map((f) => f.key))

  function apply(s: AdminSettings) {
    data.value = s
    for (const f of s.fields) drafts[f.key] = structuredClone(f.value)
  }
  async function load() {
    loading.value = true
    try {
      apply(await api.adminSettings())
    } catch (e) {
      toast.error(e, '加载运行参数失败')
    } finally {
      loading.value = false
    }
  }
  async function save() {
    const values: Record<string, SettingValue> = {}
    for (const k of dirtyKeys.value) values[k] = drafts[k]
    if (!Object.keys(values).length) return
    saving.value = true
    try {
      apply(await api.putAdminSettings(values))
      toast.push('已保存，新任务立即生效', 'success')
    } catch (e) {
      toast.error(e, '保存失败')
    } finally {
      saving.value = false
    }
  }
  function discard() {
    for (const f of fields.value) drafts[f.key] = structuredClone(f.value)
  }
  async function reset(key: string) {
    try {
      const keepDrafts = Object.fromEntries(dirtyKeys.value.filter((k) => k !== key).map((k) => [k, drafts[k]]))
      apply(await api.resetAdminSetting(key))
      Object.assign(drafts, keepDrafts)
      toast.push('已恢复为 config.yaml 中的值', 'success')
    } catch (e) {
      toast.error(e)
    }
  }
  onMounted(load)
  return { data, drafts, fields, loading, saving, dirtyKeys, save, discard, reset, reload: load }
}
