<script setup lang="ts">
import { PageHeader, StatusBadge } from '@srbg/ui'
import { computed } from 'vue'

import SourceCoverageMatrix from '../../../components/SourceCoverageMatrix.vue'
import type { SourceCoverageResponse } from '../../../source-center'

const {
  data: coverage,
  error,
  refresh,
  status,
} = await useFetch<SourceCoverageResponse>('/api/v1/admin/source-coverage', {
  default: () => ({ cells: [], gap_cell_count: 0, generated_at: new Date(0).toISOString() }),
  retry: 0,
  timeout: 5_000,
})

const gapCount = computed(() => coverage.value.gap_cell_count)
</script>

<template>
  <section class="coverage-page">
    <PageHeader
      title="来源覆盖缺口"
      eyebrow="来源中心 V2"
      description="按工程行业 × 内容域 × 来源类型 × 地区 / 语言识别缺口；候选与试运行只作为储备，只有 ACTIVE 计入生产覆盖。"
      :updated-at="coverage.generated_at"
      updated-label="矩阵生成时间"
    >
      <template #status>
        <StatusBadge :tone="gapCount > 0 ? 'conflict' : 'healthy'" :label="`${gapCount} 个覆盖缺口`" />
        <span>UNKNOWN 维度保持显式，不从名称或 URL 猜测</span>
      </template>
      <template #actions>
        <NuxtLink class="secondary-button" to="/admin/sources">返回来源中心</NuxtLink>
      </template>
    </PageHeader>

    <p v-if="error" class="problem" role="alert">
      覆盖矩阵暂不可用；系统没有用候选网址数量替代覆盖事实。
      <button type="button" @click="refresh()">重试</button>
    </p>
    <p v-else-if="status === 'pending'" class="loading" aria-live="polite">正在计算覆盖缺口…</p>
    <SourceCoverageMatrix v-else :cells="coverage.cells" />
  </section>
</template>

<style scoped>
.coverage-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.secondary-button {
  display: inline-flex;
  min-height: var(--spacing-10);
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2) var(--spacing-4);
  color: var(--color-brand-700);
  background: var(--color-surface);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
}

.problem {
  margin: 0;
  padding: var(--spacing-3);
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
}

.loading {
  padding: var(--spacing-8);
  color: var(--color-ink-600);
  text-align: center;
}
</style>
