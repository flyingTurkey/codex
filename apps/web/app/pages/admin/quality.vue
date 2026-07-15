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
    title="质量看板"
    description="显示审核与发布门禁的当前窗口信号；长期 SLO 结论仅由版本化证据包生成。"
    :overview="data"
    :metric-codes="['PENDING_REVIEWS', 'PUBLISHER_OUTBOX_DEPTH', 'FAILED_TASKS']"
  />
  <p v-else-if="error" role="alert">质量数据加载失败，请检查 API 与权限。</p>
  <p v-else aria-live="polite">{{ status === 'pending' ? '正在加载质量数据…' : '暂无质量数据' }}</p>
</template>
