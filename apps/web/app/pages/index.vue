<script setup lang="ts">
import type { ProblemDetails, VersionResponse } from '@srbg/contracts'

import { createUuidV7 } from '../utils/uuid-v7'

const config = useRuntimeConfig()
const versionCheckRequestId = useState('api-version-request-id', () => createUuidV7())
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
    request_id: versionCheckRequestId.value,
    status: 503,
    title: '工程基线连接暂不可用',
    type: 'about:blank',
  }
})
</script>

<template>
  <HomeDashboard :problem="problem" :version="problem ? null : (version ?? null)" />
</template>
