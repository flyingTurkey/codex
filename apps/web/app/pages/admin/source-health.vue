<script setup lang="ts">
import type { OperationsOverview, ReplayTaskView, SourceHealthView } from '@srbg/contracts'

const { data, error, status } = await useFetch<OperationsOverview>(
  '/api/v1/admin/operations/overview',
  { server: false },
)
const { data: health } = await useFetch<SourceHealthView[]>(
  '/api/v1/admin/operations/source-health',
  { server: false, default: () => [] },
)
const { data: replays } = await useFetch<ReplayTaskView[]>(
  '/api/v1/admin/operations/replays',
  { server: false, default: () => [] },
)
</script>

<template>
  <div class="source-health-page">
    <OperationsDashboard
      v-if="data"
      title="来源健康"
      description="区分传输、发现、解析、内容质量与业务新鲜度，并显示数据库权威恢复状态。"
      :overview="data"
      :metric-codes="['UNHEALTHY_SOURCES', 'OPEN_SOURCE_CIRCUITS', 'FETCH_BACKLOG_AGE_SECONDS', 'SOURCE_SLO_VIOLATIONS']"
    />
    <p v-else-if="error" role="alert">来源健康数据加载失败，请检查 API 与权限。</p>
    <p v-else aria-live="polite">{{ status === 'pending' ? '正在加载来源健康…' : '暂无来源健康数据' }}</p>

    <section aria-labelledby="source-anomalies-title">
      <h2 id="source-anomalies-title">异常待办</h2>
      <p v-if="!health.length">当前没有数据库记录的来源异常。</p>
      <article v-for="snapshot in health" :key="snapshot.fetch_run_id" class="evidence-card">
        <h3>{{ snapshot.source_id }}</h3>
        <p>传输 {{ snapshot.transport_status }} · 发现 {{ snapshot.discovery_status }} · 解析 {{ snapshot.parse_status }} · 质量 {{ snapshot.quality_status }} · 时效 {{ snapshot.freshness_status }}</p>
        <ul><li v-for="anomaly in snapshot.anomalies" :key="anomaly.id">{{ anomaly.severity }} · {{ anomaly.code }} · {{ anomaly.status }}</li></ul>
      </article>
    </section>

    <section aria-labelledby="safe-replay-title">
      <h2 id="safe-replay-title">安全重放</h2>
      <p v-if="!replays.length">当前没有未解决的失败任务。</p>
      <article v-for="task in replays" :key="task.id" class="evidence-card">
        <h3>{{ task.task_kind }} · {{ task.reconstruction_status }}</h3>
        <p>{{ task.error_code }} · {{ task.blocked_reason ?? '可从权威引用重建' }}</p>
      </article>
    </section>
  </div>
</template>

<style scoped>
.source-health-page { display: grid; gap: var(--spacing-6); }
.source-health-page section { display: grid; gap: var(--spacing-3); }
.evidence-card { padding: var(--spacing-4); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
.evidence-card h3, .evidence-card p { margin: 0; }
</style>
