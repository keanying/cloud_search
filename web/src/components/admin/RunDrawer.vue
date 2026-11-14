<script setup lang="ts">
import { computed } from 'vue'
import { ListChecks } from 'lucide-vue-next'
import type { AdminAgentRun } from '@/api/types'
import StatusPill from '@/components/admin/StatusPill.vue'
import SideDrawer from '@/components/common/SideDrawer.vue'
import { compact, duration, money, runStatus } from '@/lib/adminFormat'
import { formatTime } from '@/lib/format'

/** 模型调用详情抽屉（数据来自列表行）：完整错误、token、费用、耗时、所属任务 */
const props = defineProps<{ run: AdminAgentRun | null }>()
const emit = defineEmits<{ close: []; openTask: [taskId: string] }>()
const open = computed({ get: () => !!props.run, set: (v: boolean) => !v && emit('close') })
</script>

<template>
  <SideDrawer v-model="open" title="调用详情" :width="560">
    <template #title>
      <div v-if="run" class="min-w-0">
        <div class="flex items-center gap-2">
          <StatusPill :tone="runStatus(run.run_status).tone" :text="runStatus(run.run_status).label" />
          <span class="text-[12px] text-slate-400">{{ formatTime(run.started_time) }}</span>
        </div>
        <h2 class="mt-1.5 text-base font-bold tracking-tight text-white">{{ run.role_label }} · {{ run.model_name || '未知模型' }}</h2>
        <div class="font-mono text-[11px] text-slate-500">{{ run.agent_run_id }}</div>
      </div>
    </template>
    <template v-if="run">
      <div v-if="run.error_desc" class="mb-5">
        <div class="ac-caps mb-1.5">错误信息</div>
        <code class="ac-code">{{ run.error_desc }}</code>
      </div>
      <dl class="ac-dl">
        <dt>智能体</dt>
        <dd>{{ run.role_label }} <span class="font-mono text-[11px] text-slate-500">{{ run.agent_role }}</span></dd>
        <dt>模型</dt>
        <dd>{{ run.model_name || '—' }}<span v-if="run.provider_name" class="text-slate-400"> · {{ run.provider_name }}</span></dd>
        <dt>请求次数</dt>
        <dd class="tabular-nums">{{ run.request_qty }}</dd>
        <dt>Token</dt>
        <dd class="tabular-nums">输入 {{ compact(run.input_token_qty) }} · 输出 {{ compact(run.output_token_qty) }}</dd>
        <dt>费用</dt>
        <dd>
          <span v-if="run.cost_status === 'unknown'" class="text-amber-300">待核算（模型未配置单价）</span>
          <span v-else class="tabular-nums">{{ money(run.cost_minor_amt, run.currency_code) }}</span>
        </dd>
        <dt>耗时</dt>
        <dd class="tabular-nums">{{ duration(run.duration_ms) }}</dd>
        <dt>开始 / 结束</dt>
        <dd class="tabular-nums">{{ formatTime(run.started_time) }} — {{ run.finished_time ? formatTime(run.finished_time) : '—' }}</dd>
        <dt>所属任务</dt>
        <dd>
          <button v-if="run.task_id" type="button" class="inline-flex items-center gap-1.5 font-mono text-[12px] text-brand-300 hover:underline" @click="emit('openTask', run.task_id)">
            <ListChecks class="h-3.5 w-3.5" /> {{ run.task_id }}
          </button>
          <span v-else class="text-slate-500">—（对话轮次中的调用）</span>
        </dd>
      </dl>
    </template>
  </SideDrawer>
</template>
