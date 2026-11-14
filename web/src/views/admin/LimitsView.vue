<script setup lang="ts">
import { Info, Loader2 } from 'lucide-vue-next'
import AdminPage from '@/components/admin/AdminPage.vue'
import SaveBar from '@/components/admin/SaveBar.vue'
import SettingFieldControl from '@/components/admin/SettingFieldControl.vue'
import { useAdminSettings } from '@/lib/useAdminSettings'

const s = useAdminSettings(['task'])
</script>

<template>
  <AdminPage>
    <div v-if="s.loading.value && !s.data.value" class="flex items-center gap-2 text-sm text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> 加载中…</div>
    <template v-else>
      <div class="mb-5 flex gap-3 rounded-3xl card-sky p-5 text-sm leading-6 accent-ink">
        <Info class="mt-0.5 h-5 w-5 shrink-0" />
        <p>
          这些是单个任务的默认上限，对之后新开始的任务生效。需求编译智能体会在上限内按需求规模取值（例如“越多越好”也不会超过上限）。
          上限越高，结果越全面，但耗时与模型费用也越高。
        </p>
      </div>
      <div class="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        <SettingFieldControl
          v-for="f in s.fields.value"
          :key="f.key"
          v-model="s.drafts[f.key]"
          class="surface !bg-[var(--cs-surface-solid)]"
          :field="f"
          :dirty="s.dirtyKeys.value.includes(f.key)"
          @reset="s.reset(f.key)"
        />
      </div>
    </template>
    <SaveBar :count="s.dirtyKeys.value.length" :saving="s.saving.value" @save="s.save()" @discard="s.discard()" />
  </AdminPage>
</template>
