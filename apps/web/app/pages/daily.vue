<script setup lang="ts">
import type { DailyReport, MeResponse, ProblemDetails } from '@srbg/contracts'
import { computed, ref } from 'vue'

import DailyReportView from '../components/DailyReportView.vue'
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { createUuidV7 } from '../utils/uuid-v7'

const { data: report, error, refresh, status } = await useFetch<DailyReport>('/api/v1/daily', {
  server: false, retry: 0, timeout: 5_000,
})
const { data: me } = await useFetch<MeResponse>('/api/v1/me', { server: false, retry: 0 })
const busy = ref(false)
const problem = computed(() => error.value?.data as ProblemDetails ?? null)
const canReview = computed(() => me.value?.roles.some(role => ['reviewer', 'platform_admin'].includes(role)) ?? false)

async function createDraft(): Promise<void> {
  busy.value = true
  try {
    report.value = await $fetch('/api/v1/admin/daily/drafts', {
      method: 'POST', body: { report_date: new Date().toISOString().slice(0, 10) },
      headers: { 'Idempotency-Key': createUuidV7() },
    })
  }
  finally { busy.value = false }
}

async function publish(): Promise<void> {
  if (!report.value) return
  busy.value = true
  try {
    report.value = await $fetch(`/api/v1/admin/daily/${report.value.id}/publish`, {
      method: 'POST', headers: { 'Idempotency-Key': createUuidV7() },
    })
  }
  finally { busy.value = false }
}
</script>

<template>
  <IntelligenceFeedPage
    title="行业日报"
    eyebrow="固定快照 · 审核后发布"
    description="日报不会在发布后静默重排；撤回和原文失效状态会实时覆盖旧摘要。"
    empty-title="当天日报尚未发布"
    empty-description="审核员生成草稿并完成发布后会在这里出现。"
    :loading="status === 'idle' || status === 'pending'"
    :problem="problem"
    @retry="refresh"
  >
    <template #actions>
      <div class="daily-actions">
        <button v-if="canReview && !report" type="button" :disabled="busy" @click="createDraft">生成今日草稿</button>
        <button v-if="canReview && report?.status === 'DRAFT'" type="button" :disabled="busy || report.requires_regeneration" @click="publish">审核通过并发布</button>
        <a v-if="report?.status === 'PUBLISHED'" :href="`/api/v1/export/markdown?report_id=${report.id}`">导出 Markdown</a>
      </div>
    </template>
    <DailyReportView v-if="report" :report="report" />
  </IntelligenceFeedPage>
</template>

<style scoped>
.daily-actions { display: flex; flex-wrap: wrap; gap: var(--spacing-2); }
.daily-actions button,
.daily-actions a { padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); background: var(--color-surface); }
</style>
