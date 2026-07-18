<script setup lang="ts">
import type { DailyReport } from '@srbg/contracts'
import { StatusBadge } from '@srbg/ui'
import { computed } from 'vue'

const props = defineProps<{ report: DailyReport }>()
const isAutomaticPersonalReport = computed(() =>
  props.report.sections.some(section => ['EVIDENCE_FACTS', 'AI_JUDGMENTS', 'UNVERIFIED_AI', 'AI_PROCESSING_FAILURES'].includes(section.kind)),
)
const resultLabels = {
  EVIDENCE_FACT: '证据事实', AI_JUDGMENT: 'AI 判断',
  UNVERIFIED_AI: '未验证 AI', AI_PROCESSING_FAILED: 'AI 处理失败',
} as const
</script>

<template>
  <article class="daily-report" :data-status="report.status">
    <header>
      <div>
        <p>固定快照 · {{ report.report_date }}</p>
        <h2>四川路桥行业数智与安全日报</h2>
      </div>
      <StatusBadge
        :tone="report.status === 'PUBLISHED' ? 'verified' : 'pending'"
        :label="isAutomaticPersonalReport ? '自动发布' : report.status === 'PUBLISHED' ? '已审核发布' : '审核草稿'"
      />
    </header>
    <p v-if="report.requires_regeneration" class="daily-report__warning" role="alert">
      来源或发布版本已变化，请重新生成草稿后再发布。
    </p>
    <section v-for="section in report.sections" :key="section.kind">
      <h3>{{ section.title }}</h3>
      <ol v-if="section.items.length">
        <li v-for="item in section.items" :key="item.event_id ?? item.item_id ?? item.position">
          <div>
            <a :href="`/events/${item.event_id ?? item.item_id}`">{{ item.title }}</a>
            <strong v-if="item.current_state === 'WITHDRAWN'">已撤回</strong>
            <strong v-else-if="item.current_state === 'SOURCE_UNAVAILABLE'">原文失效</strong>
            <strong v-if="item.automatic_result_type">{{ resultLabels[item.automatic_result_type] }}</strong>
          </div>
          <p v-if="item.summary && item.current_state === 'PUBLISHED'">{{ item.summary }}</p>
        </li>
      </ol>
      <p v-else class="daily-report__empty">本节暂无条目。</p>
    </section>
  </article>
</template>

<style scoped>
.daily-report {
  display: grid;
  width: min(100%, 48rem);
  margin-inline: auto;
  padding: var(--spacing-6);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  gap: var(--spacing-5);
}

.daily-report header,
.daily-report li > div {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-3);
}

.daily-report header p,
.daily-report h2,
.daily-report h3,
.daily-report li p { margin: 0; }
.daily-report header p,
.daily-report__empty { color: var(--color-ink-600); font-size: var(--text-sm); }
.daily-report section { display: grid; gap: var(--spacing-3); }
.daily-report ol { display: grid; margin: 0; padding-left: var(--spacing-5); gap: var(--spacing-3); }
.daily-report li p { margin-top: var(--spacing-1); color: var(--color-ink-700); }
.daily-report li strong { color: var(--color-conflict-700); font-size: var(--text-xs); }
.daily-report__warning {
  margin: 0;
  padding: var(--spacing-3);
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
  border-radius: var(--radius-sm);
}

@media (max-width: 47.999rem) {
  .daily-report { padding: var(--spacing-4); }
  .daily-report header { display: grid; }
}
</style>
