<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDown, ArrowUp, GripVertical, Minus, Plus, RotateCcw } from 'lucide-vue-next'
import type { SettingField, SettingValue } from '@/api/types'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
import ToggleSwitch from '@/components/common/ToggleSwitch.vue'

/** 按字段类型渲染控件：引擎顺序 / 分段 / 多选胶囊 / 数字 / 开关；显示“已覆盖”与恢复默认 */
const props = defineProps<{ field: SettingField; dirty: boolean }>()
const emit = defineEmits<{ reset: [] }>()
const model = defineModel<SettingValue>({ required: true })

const id = computed(() => `sf-${props.field.key}`)
const optLabel = (v: string) => props.field.options?.find((o) => o.value === v)?.label ?? v

// ---------------------------------------------------------------- 引擎顺序：启用的在前（按顺序），未启用的在后
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

// ---------------------------------------------------------------- 多选
const multi = computed<string[] | null>(() => (Array.isArray(model.value) ? (model.value as string[]) : null))
function toggleMulti(v: string) {
  // null 表示“全部可用”：第一次点击时从全部展开
  const cur = multi.value ?? (props.field.options ?? []).map((o) => o.value)
  model.value = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]
}
const multiOn = (v: string) => (multi.value ? multi.value.includes(v) : true)

// ---------------------------------------------------------------- 数字
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
</script>

<template>
  <div class="field" :class="dirty ? 'field-dirty' : ''">
    <div class="flex flex-wrap items-start gap-x-3 gap-y-2">
      <div class="min-w-0 flex-1">
        <label :for="id" class="flex flex-wrap items-center gap-2 text-sm font-semibold text-white">
          {{ field.label }}
          <span v-if="dirty" class="pill card-butter !py-0 text-[11px] accent-ink">未保存</span>
          <span v-else-if="field.overridden" class="pill card-sky !py-0 text-[11px] accent-ink">已修改（覆盖 config.yaml）</span>
        </label>
        <p v-if="field.help" class="mt-0.5 text-xs leading-5 text-slate-400">{{ field.help }}</p>
      </div>
      <button v-if="field.overridden" type="button" class="btn-ghost btn-sm !px-2" title="恢复为 config.yaml 中的值" @click="emit('reset')">
        <RotateCcw class="h-3.5 w-3.5" /> 恢复默认
      </button>
      <!-- 简单控件放在右侧 -->
      <ToggleSwitch v-if="field.type === 'bool'" :id="id" v-model="bool" :label="field.label" />
      <div v-else-if="field.type === 'int'" class="flex items-center gap-1">
        <button type="button" class="round-btn-light !h-9 !w-9" aria-label="减少" @click="step(-1)"><Minus class="h-3.5 w-3.5" /></button>
        <input
          :id="id"
          v-model.number="num"
          type="number"
          class="input !w-24 !rounded-full !py-1.5 text-center tabular-nums"
          :class="outOfRange ? '!border-rose-300' : ''"
          :min="field.min ?? undefined"
          :max="field.max ?? undefined"
        />
        <button type="button" class="round-btn-light !h-9 !w-9" aria-label="增加" @click="step(1)"><Plus class="h-3.5 w-3.5" /></button>
      </div>
      <SegmentedControl v-else-if="field.type === 'select'" :id="id" v-model="seg" small :label="field.label" :options="field.options ?? []" />
    </div>
    <p v-if="field.type === 'int' && (field.min != null || field.max != null)" class="mt-1 text-right text-[11px] text-slate-500" :class="outOfRange ? '!text-rose-300' : ''">
      范围 {{ field.min ?? '—' }} – {{ field.max ?? '—' }}<template v-if="field.default != null"> · 默认 {{ field.default }}</template>
    </p>

    <!-- 引擎顺序 -->
    <div v-if="field.type === 'engine_order'" class="mt-3 space-y-1.5">
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
        <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--cs-ink)] text-[11px] font-bold text-[var(--cs-on-ink)]">{{ i + 1 }}</span>
        <span class="min-w-0 flex-1">
          <span class="text-sm font-semibold text-white">{{ optLabel(v) }}</span>
          <span class="ml-2 font-mono text-[11px] text-slate-500">{{ v }}</span>
        </span>
        <button type="button" class="icon-btn !h-7 !w-7" :disabled="i === 0" :aria-label="`上移 ${optLabel(v)}`" @click="move(i, -1)"><ArrowUp class="h-3.5 w-3.5" /></button>
        <button type="button" class="icon-btn !h-7 !w-7" :disabled="i === order.length - 1" :aria-label="`下移 ${optLabel(v)}`" @click="move(i, 1)"><ArrowDown class="h-3.5 w-3.5" /></button>
        <ToggleSwitch small :model-value="true" :label="`停用 ${optLabel(v)}`" :disabled="order.length <= 1" @update:model-value="toggleEngine(v, false)" />
      </div>
      <div v-for="v in disabledOpts" :key="v" class="engine-row opacity-60">
        <span class="h-4 w-4 shrink-0" />
        <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-dashed border-slate-500 text-[11px] text-slate-500">–</span>
        <span class="min-w-0 flex-1">
          <span class="text-sm font-semibold text-white">{{ optLabel(v) }}</span>
          <span class="ml-2 font-mono text-[11px] text-slate-500">{{ v }}</span>
          <span class="ml-2 text-[11px] text-slate-500">未启用</span>
        </span>
        <ToggleSwitch small :model-value="false" :label="`启用 ${optLabel(v)}`" @update:model-value="toggleEngine(v, true)" />
      </div>
    </div>

    <!-- 多选胶囊 -->
    <div v-else-if="field.type === 'multi'" class="mt-3 flex flex-wrap gap-1.5">
      <button
        v-for="o in field.options ?? []"
        :key="o.value"
        type="button"
        class="chip !py-1 !text-xs"
        :class="multiOn(o.value) ? 'chip-active' : ''"
        :aria-pressed="multiOn(o.value)"
        @click="toggleMulti(o.value)"
      >
        {{ o.label }}
      </button>
      <span v-if="multi === null" class="self-center text-[11px] text-slate-500">（全部可用）</span>
    </div>
  </div>
</template>

<style scoped>
.field {
  padding: 1rem 1.15rem;
  border-radius: 20px;
  background: var(--cs-surface-sunken);
  border: 1px solid transparent;
  transition: border-color 0.15s ease;
}
.field-dirty {
  border-color: var(--pastel-butter-dot);
}
.engine-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.6rem 0.5rem 0.4rem;
  border-radius: 14px;
  background: var(--cs-surface-solid);
  border: 1px solid var(--cs-line);
}
</style>
