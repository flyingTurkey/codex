<script setup lang="ts">
import type { ProblemDetails, VersionResponse } from '@srbg/contracts'

const config = useRuntimeConfig()
const { data: version, error } = await useAsyncData('api-version', () =>
  $fetch<VersionResponse>(`${config.internalApiBase}/api/v1/version`, {
    retry: 0,
    timeout: 2_000,
  }),
)

const problem = computed<ProblemDetails | null>(() => {
  if (!error.value) return null

  return {
    detail: '版本服务暂时无法响应，请稍后重试。',
    request_id: 'web-version-check',
    status: 503,
    title: '工程基线连接暂不可用',
    type: 'about:blank',
  }
})
</script>

<template>
  <HomeDashboard :problem="problem" :version="problem ? null : (version ?? null)" />
</template>
