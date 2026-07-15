<script setup lang="ts">
import type { OperationsOverview } from '@srbg/contracts'
import { computed } from 'vue'

const props = defineProps<{
  title: string
  description: string
  overview: OperationsOverview
  metricCodes?: string[]
}>()

const labels: Record<string, string> = {
  UNHEALTHY_SOURCES: '异常来源',
  OPEN_SOURCE_CIRCUITS: '已熔断来源',
  PENDING_REVIEWS: '待审核',
  PUBLISHER_OUTBOX_DEPTH: '发布队列',
  FAILED_TASKS: '失败任务',
  QUEUED_REPLAYS: '待重放',
  AI_FAILURES_24H: 'AI 失败（24小时）',
  AI_COST_MICROUSD_24H: 'AI 成本（24小时）',
  AI_LATENCY_P95_MS_24H: 'AI 延迟 P95（24小时）',
  AI_COST_PER_DOCUMENT_MICROUSD_24H: '单文档 AI 成本（24小时）',
}

const statusLabels: Record<string, string> = {
  PASS: '通过',
  FAIL: '失败',
  UNKNOWN: '待观察',
}

const visibleMetrics = computed(() => props.overview.metrics.filter(metric => (
  !props.metricCodes || props.metricCodes.includes(metric.code)
)))

const observedAt = computed(() => new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
  timeZone: 'Asia/Shanghai',
}).format(new Date(props.overview.observed_at)))
</script>

<template>
  <section class="operations-dashboard" aria-labelledby="operations-title">
    <header class="operations-dashboard__header">
      <div>
        <p class="operations-dashboard__eyebrow">运行与质量证据</p>
        <h1 id="operations-title">{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <p class="operations-dashboard__time">
        观测时间
        <time :datetime="overview.observed_at">{{ observedAt }}</time>
      </p>
    </header>

    <section class="operations-dashboard__grid" aria-label="指标状态">
      <article v-for="metric in visibleMetrics" :key="metric.code" class="operations-metric">
        <div class="operations-metric__heading">
          <h2>{{ labels[metric.code] ?? metric.code }}</h2>
          <span :class="`operations-metric__status operations-metric__status--${metric.status.toLowerCase()}`">
            {{ statusLabels[metric.status] ?? metric.status }}
          </span>
        </div>
        <p class="operations-metric__value">
          {{ metric.value }} <small>{{ metric.unit }}</small>
        </p>
        <code>{{ metric.code }}</code>
      </article>
    </section>
  </section>
</template>

<style scoped>
.operations-dashboard {
  display: grid;
  gap: var(--spacing-6);
}

.operations-dashboard__header {
  display: flex;
  gap: var(--spacing-4);
  align-items: flex-start;
  justify-content: space-between;
  padding: var(--spacing-6);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.operations-dashboard__header h1,
.operations-metric h2,
.operations-dashboard__header p {
  margin: 0;
}

.operations-dashboard__eyebrow {
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.operations-dashboard__time {
  display: grid;
  flex: 0 0 auto;
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  text-align: right;
}

.operations-dashboard__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr));
  gap: var(--spacing-4);
}

.operations-metric {
  padding: var(--spacing-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

.operations-metric__heading {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
  justify-content: space-between;
}

.operations-metric h2 {
  font-size: var(--text-base);
}

.operations-metric__status {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-pill);
  color: var(--color-ink-800);
  background: var(--color-surfaceMuted);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
}

.operations-metric__status--pass {
  color: var(--color-verified-700);
  background: var(--color-verified-50);
}

.operations-metric__status--fail {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

.operations-metric__value {
  margin: var(--spacing-5) 0 var(--spacing-3);
  color: var(--color-ink-900);
  font-size: var(--text-3xl);
  font-weight: var(--font-weight-bold);
}

.operations-metric__value small,
.operations-metric code {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

@media (max-width: 48rem) {
  .operations-dashboard__header {
    flex-direction: column;
  }

  .operations-dashboard__time {
    text-align: left;
  }
}
</style>
