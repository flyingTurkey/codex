<script setup lang="ts">
import type { DailyReport, ProblemDetails } from '@srbg/contracts'
import { computed } from 'vue'

import DailyReportView from '../components/DailyReportView.vue'
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'

const { data: report, error, refresh, status } = await useFetch<DailyReport>('/api/v1/daily', {
  server: false, retry: 0, timeout: 5_000,
})
const problem = computed(() => error.value?.data as ProblemDetails ?? null)
const isAutomaticPersonalReport = computed(() => report.value?.sections.some(
  section => section.kind === 'EVIDENCE_FACTS' || section.kind === 'UNVERIFIED_AI',
) ?? false)
</script>

<template>
  <IntelligenceFeedPage
    title="行业日报"
    eyebrow="固定快照 · PublicationService 自动发布"
    description="日报分为证据事实和未验证 AI；撤回、纠正或原文变化会使旧快照立即不可达。"
    empty-title="当天日报尚未发布"
    empty-description="当天尚无可投影的证据事实或未验证 AI。"
    :loading="status === 'idle' || status === 'pending'"
    :problem="problem"
    @retry="refresh"
  >
    <template #actions>
      <div class="daily-actions">
        <a
          v-if="report?.status === 'PUBLISHED' && !isAutomaticPersonalReport"
          :href="`/api/v1/export/markdown?report_id=${report.id}`"
        >导出 Markdown</a>
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
