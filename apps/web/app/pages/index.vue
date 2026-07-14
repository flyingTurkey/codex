<script setup lang="ts">
import type { ProblemDetails, VersionResponse } from '@srbg/contracts'

import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'
import { createUuidV7 } from '../utils/uuid-v7'

const { data: feed, status } = await useIntelligenceFeed('selected')
const versionCheckRequestId = useState('api-version-request-id', () => createUuidV7())
const versionCheckedAt = useState<string | null>('api-version-checked-at', () => null)
const { data: version, error: versionError } = await useFetch<VersionResponse>('/api/v1/version', {
  retry: 0,
  timeout: 2_000,
})
if (!versionError.value && version.value && versionCheckedAt.value === null) {
  versionCheckedAt.value = new Date().toISOString()
}
const problem = computed<ProblemDetails | null>(() =>
  versionError.value
    ? {
        detail: '版本服务暂时无法响应，请稍后重试。',
        request_id: versionCheckRequestId.value,
        status: 503,
        title: '工程基线连接暂不可用',
        type: 'about:blank',
      }
    : null,
)
</script>

<template>
  <IntelligenceFeedPage
    title="今日精选"
    eyebrow="精选发布"
    description="只有通过真实评分与发布门禁的内容才会进入精选。"
    status-label="真实评分待接入"
    status-tone="info"
    empty-title="暂无精选内容"
    empty-description="第 08 轮前缺少真实评分的内容不会进入精选，也不会展示演示分数。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :updated-at="versionCheckedAt ?? undefined"
  >
    <template #status-detail>
      <span v-if="version">API {{ version.api_version }} · Schema {{ version.content_schema_version }}</span>
    </template>
    <template v-if="problem" #notice>
      <p role="alert">{{ problem.title }}：{{ problem.detail }}</p>
    </template>
  </IntelligenceFeedPage>
</template>
