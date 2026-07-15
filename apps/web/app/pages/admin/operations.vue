<script setup lang="ts">
import type { OperationsOverview } from '@srbg/contracts'

const { data, error, status } = await useFetch<OperationsOverview>(
  '/api/v1/admin/operations/overview',
  { server: false },
)
</script>

<template>
  <OperationsDashboard
    v-if="data"
    title="运行中心"
    description="聚合队列、失败任务和人工重放状态；重放仍受服务端权限与幂等门禁约束。"
    :overview="data"
    :metric-codes="[
      'PUBLISHER_OUTBOX_DEPTH',
      'FAILED_TASKS',
      'QUEUED_REPLAYS',
      'AI_FAILURES_24H',
      'AI_COST_MICROUSD_24H',
      'AI_LATENCY_P95_MS_24H',
      'AI_COST_PER_DOCUMENT_MICROUSD_24H',
    ]"
  />
  <p v-else-if="error" role="alert">运行数据加载失败，请检查 API 与权限。</p>
  <p v-else aria-live="polite">{{ status === 'pending' ? '正在加载运行数据…' : '暂无运行数据' }}</p>
</template>
