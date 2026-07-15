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
    title="来源健康"
    description="查看来源失败、熔断与恢复状态；数据来自当前运行窗口。"
    :overview="data"
    :metric-codes="['UNHEALTHY_SOURCES', 'OPEN_SOURCE_CIRCUITS']"
  />
  <p v-else-if="error" role="alert">来源健康数据加载失败，请检查 API 与权限。</p>
  <p v-else aria-live="polite">{{ status === 'pending' ? '正在加载来源健康…' : '暂无来源健康数据' }}</p>
</template>
