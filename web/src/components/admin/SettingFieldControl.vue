<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDown, ArrowUp, GripVertical, Minus, Plus } from 'lucide-vue-next'
import type { SettingField, SettingValue } from '@/api/types'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
import ToggleSwitch from '@/components/common/ToggleSwitch.vue'

/**
 * 运行参数的一行：左侧 标签 + 说明 + 状态（已修改 / 覆盖 config.yaml · 恢复默认），右侧 控件。
 * 控件按类型渲染：引擎顺序（拖动/上下移/开关）、分段、多选、数字步进、开关。
 */
const props = defineProps<{ field: SettingField; dirty: boolean }>()
const emit = defineEmits<{ reset: [] }>()
const model = defineModel<SettingValue>({ required: true })

const id = computed(() => `sf-${props.field.key}`)
const optLabel = (v: string) => props.field.options?.find((o) => o.value === v)?.label ?? v

// 引擎顺序：启用的在前（按顺序），未启用的在后
const order = computed<string[]>(() => (Array.isArray(model.value) ? (model.value as string[]) : []))
const disabledOpts = computed(() => (props.field.options ?? []).map((o) => o.value).filter((v) => !order.value.includes(v)))
function move(i: number, d: number) {
  const a = [...order.value]
  const j = i + d
  if (j < 0 || j >= a.length) return
  ;[a[i], a[j]] = [a[j], a[i]]
  model.value = a
}
function toggleEngine(v: string, on: boolean) {
  model.value = on ? [...order.value, v] : order.value.filter((x) => x !== v)
}
const dragFrom = ref<number | null>(null)
function onDrop(i: number) {
  if (dragFrom.value == null || dragFrom.value === i) return
  const a = [...order.value]
  const [x] = a.splice(dragFrom.value, 1)
  a.splice(i, 0, x)
  model.value = a
  dragFrom.value = null
}

// 多选（null = 全部）
const multi = computed<string[] | null>(() => (Array.isArray(model.value) ? (model.value as string[]) : null))
function toggleMulti(v: string) {
  const cur = multi.value ?? (props.field.options ?? []).map((o) => o.value)
  model.value = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
}
const multiOn = (v: string) => (multi.value ? multi.value.includes(v) : true)

// 数字
const num = computed({
  get: () => (typeof model.value === 'number' ? model.value : Number(model.value ?? 0)),
  set: (v: number) => (model.value = v),
})
function step(d: number) {
  let v = num.value + d
  if (props.field.min != null) v = Math.max(props.field.min, v)
  if (props.field.max != null) v = Math.min(props.field.max, v)
  num.value = v
}
const outOfRange = computed(
  () =>
    props.field.type === 'int' &&
    ((props.field.min != null && num.value < props.field.min) || (props.field.max != null && num.value > props.field.max)),
)
const bool = computed({ get: () => !!model.value, set: (v: boolean) => (model.value = v) })
const seg = computed({ get: () => String(model.value ?? ''), set: (v: string) => (model.value = v) })
const defaultText = computed(() => {
  const d = props.field.default
  if (d == null) return ''
  if (typeof d === 'boolean') return d ? '开' : '关'
  if (Array.isArray(d)) return d.map((x) => optLabel(String(x))).join('、')
  return props.field.type === 'select' ? optLabel(String(d)) : String(d)
})
</script>

<template>
  <div class="ac-row" :class="dirty ? 'row-dirty' : ''">
    <div class="min-w-0">
      <label :for="id" class="flex flex-wrap items-center gap-2 text-[13px] font-semibold text-white">
        {{ field.label }}
        <span v-if="dirty" class="inline-flex items-center gap-1 text-[11px] font-medium text-amber-300">
          <span class="h-1.5 w-1.5 rounded-full bg-[var(--pastel-butter-dot)]" />已修改
        </span>
      </label>
      <p v-if="field.help" class="mt-1 text-[12px] leading-5 text-slate-400">{{ field.help }}</p>
      <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
        <span v-if="field.type === 'int' && (field.min != null || field.max != null)" :class="outOfRange ? 'text-rose-300' : ''">
          范围 {{ field.min ?? '—' }}–{{ field.max ?? '—' }}
        </span>
        <span v-if="defaultText && field.type !== 'engine_order' && field.type !== 'multi'">config.yaml：{{ defaultText }}</span>
        <template v-if="field.overridden">
          <span class="inline-flex items-center gap-1 text-[var(--pastel-sky-dot)]">
            <span class="h-1.5 w-1.5 rounded-full bg-[var(--pastel-sky-dot)]" />后台已覆盖
          </span>
          <button type="button" class="font-semibold text-slate-300 underline-offset-2 hover:underline" title="删除后台的覆盖值，恢复为 config.yaml 中的值" @click="emit('reset')">
            恢复默认
          </button>
        </template>
      </div>
    </div>

    <div class="flex min-w-0 items-start md:justify-end">
      <ToggleSwitch v-if="field.type === 'bool'" :id="id" v-model="bool" :label="field.label" />

      <div v-else-if="field.type === 'int'" class="flex items-center gap-1">
        <button type="button" class="round-btn-light" aria-label="减少" @click="step(-1)"><Minus class="h-3.5 w-3.5" /></button>
        <input
          :id="id"
          v-model.number="num"
          type="number"
          class="input !w-24 text-center tabular-nums"
          :class="outOfRange ? '!border-rose-300' : ''"
          :min="field.min ?? undefined"
          :max="field.max ?? undefined"
        />
        <button type="button" class="round-btn-light" aria-label="增加" @click="step(1)"><Plus class="h-3.5 w-3.5" /></button>
      </div>

      <SegmentedControl v-else-if="field.type === 'select'" :id="id" v-model="seg" small :label="field.label" :options="field.options ?? []" />

      <!-- 引擎顺序 -->
      <div v-else-if="field.type === 'engine_order'" class="w-full max-w-[520px] overflow-hidden rounded-lg border border-[var(--cs-line)]">
        <div
          v-for="(v, i) in order"
          :key="v"
          class="engine-row"
          draggable="true"
          @dragstart="dragFrom = i"
          @dragover.prevent
          @drop="onDrop(i)"
        >
          <GripVertical class="h-4 w-4 shrink-0 cursor-grab text-slate-500" aria-hidden="true" />
          <span class="w-5 shrink-0 text-center text-[12px] font-semibold text-slate-400 tabular-nums">{{ i + 1 }}</span>
          <span class="min-w-0 flex-1 truncate">
            <span class="text-[13px] font-medium text-white">{{ optLabel(v) }}</span>
            <span class="ml-2 font-mono text-[11px] text-slate-500">{{ v }}</span>
          </span>
          <button type="button" class="icon-btn !h-7 !w-7" :disabled="i === 0" :aria-label="`上移 ${optLabel(v)}`" @click="move(i, -1)"><ArrowUp class="h-3.5 w-3.5" /></button>
          <button type="button" class="icon-btn !h-7 !w-7" :disabled="i === order.length - 1" :aria-label="`下移 ${optLabel(v)}`" @click="move(i, 1)"><ArrowDown class="h-3.5 w-3.5" /></button>
          <ToggleSwitch small :model-value="true" :label="`停用 ${optLabel(v)}`" :disabled="order.length <= 1" @update:model-value="toggleEngine(v, false)" />
        </div>
        <div v-for="v in disabledOpts" :key="v" class="engine-row">
          <span class="h-4 w-4 shrink-0" />
          <span class="w-5 shrink-0 text-center text-[12px] text-slate-500">–</span>
          <span class="min-w-0 flex-1 truncate opacity-60">
            <span class="text-[13px] font-medium text-white">{{ optLabel(v) }}</span>
            <span class="ml-2 font-mono text-[11px] text-slate-500">{{ v }}</span>
            <span class="ml-2 text-[11px] text-slate-500">未启用</span>
          </span>
          <ToggleSwitch small :model-value="false" :label="`启用 ${optLabel(v)}`" @update:model-value="toggleEngine(v, true)" />
        </div>
      </div>

      <!-- 多选 -->
      <div v-else-if="field.type === 'multi'" class="flex max-w-[520px] flex-wrap gap-1.5 md:justify-end">
        <button
          v-for="o in field.options ?? []"
          :key="o.value"
          type="button"
          class="chip !px-2.5 !py-1"
          :class="multiOn(o.value) ? 'chip-active' : ''"
          :aria-pressed="multiOn(o.value)"
          @click="toggleMulti(o.value)"
        >
          {{ o.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row-dirty {
  background: color-mix(in srgb, var(--pastel-butter) 22%, transparent);
  box-shadow: inset 2px 0 0 var(--pastel-butter-dot);
}
.engine-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.6rem 0.4rem 0.5rem;
  background: var(--cs-surface-solid);
  border-top: 1px solid var(--cs-line);
}
.engine-row:first-child {
  border-top: 0;
}
</style>
