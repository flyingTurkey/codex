<script setup lang="ts">
import type { ScoreDimensionSummary, ScoreSummary } from '@srbg/contracts'
import { computed } from 'vue'

const props = defineProps<{ open: boolean, scores: ScoreSummary }>()
const emit = defineEmits<{ close: [] }>()

const labels = {
  relevance: '相关性',
  authority: '权威',
  impact: '影响',
  novelty: '新颖',
  timeliness: '时效',
  evidence: '证据',
  confidence: '置信',
  heat: '热度',
} as const

const dimensions = computed(() =>
  (Object.entries(labels) as [keyof typeof labels, string][])
    .map(([key, label]) => ({ key, label, value: props.scores[key] as ScoreDimensionSummary | null | undefined }))
    .filter((item): item is { key: keyof typeof labels, label: string, value: ScoreDimensionSummary } => Boolean(item.value)),
)
</script>

<template>
  <aside
    v-if="open"
    class="score-drawer"
    role="dialog"
    aria-modal="true"
    aria-labelledby="score-drawer-title"
    data-testid="score-breakdown"
  >
    <header>
      <div>
        <p>可解释评分</p>
        <h2 id="score-drawer-title">分项与规则依据</h2>
      </div>
      <button type="button" aria-label="关闭评分详情" @click="emit('close')">关闭</button>
    </header>
    <p class="score-drawer__notice">
      各分项相互独立；热度不参与置信分计算。缺少权威证据的分项不会生成演示分数。
    </p>
    <dl>
      <div v-for="dimension in dimensions" :key="dimension.key">
        <dt>{{ dimension.label }} {{ dimension.value.score }}</dt>
        <dd>
          <span>原始分 {{ dimension.value.raw_score }}</span>
          <span>{{ dimension.value.rule_version }}</span>
          <span v-if="dimension.value.overridden">人工覆盖：{{ dimension.value.override_reason }}</span>
          <ul>
            <li v-for="feature in dimension.value.features" :key="feature.code">
              <strong>{{ feature.label }}：{{ feature.points >= 0 ? '+' : '' }}{{ feature.points }}</strong>
              <span>{{ feature.explanation }}</span>
            </li>
          </ul>
        </dd>
      </div>
    </dl>
  </aside>
</template>

<style scoped>
.score-drawer {
  position: fixed;
  z-index: 40;
  inset-block: 0;
  inset-inline-end: 0;
  display: grid;
  width: min(100%, 34rem);
  padding: var(--spacing-5);
  overflow-y: auto;
  color: var(--color-ink-900);
  background: var(--color-surface);
  border-inline-start: 1px solid var(--color-borderStrong);
  box-shadow: var(--shadow-card);
  align-content: start;
  gap: var(--spacing-4);
}

.score-drawer header {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: var(--spacing-3);
}

.score-drawer header p,
.score-drawer header h2,
.score-drawer__notice,
.score-drawer dd,
.score-drawer ul {
  margin: 0;
}

.score-drawer header p {
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-bold);
}

.score-drawer header button {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-surfaceMuted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.score-drawer__notice {
  padding: var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-reviewPending-50);
  border-radius: var(--radius-sm);
}

.score-drawer dl {
  display: grid;
  margin: 0;
  gap: var(--spacing-3);
}

.score-drawer dl > div {
  padding: var(--spacing-4);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-md);
}

.score-drawer dt {
  color: var(--color-brand-700);
  font-weight: var(--font-weight-bold);
}

.score-drawer dd {
  display: grid;
  margin-top: var(--spacing-2);
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  gap: var(--spacing-2);
}

.score-drawer ul {
  display: grid;
  padding: 0;
  list-style: none;
  gap: var(--spacing-2);
}

.score-drawer li {
  display: grid;
  gap: var(--spacing-1);
}
</style>
