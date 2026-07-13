<script setup lang="ts">
import type { ProblemDetails, VersionResponse } from '@srbg/contracts'

import { createUuidV7 } from '../utils/uuid-v7'

const versionCheckRequestId = useState('api-version-request-id', () => createUuidV7())
const versionCheckedAt = useState<string | null>('api-version-checked-at', () => null)
const { data: version, error } = await useAsyncData('api-version', () =>
  $fetch<VersionResponse>('/api/v1/version', {
    retry: 0,
    timeout: 2_000,
  }),
)

if (!error.value && version.value && versionCheckedAt.value === null) {
  versionCheckedAt.value = new Date().toISOString()
}

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
  <HomeDashboard
    :problem="problem"
    :updated-at="problem ? null : versionCheckedAt"
    :version="problem ? null : (version ?? null)"
  />
</template>
