<script setup lang="ts">
import type { ProblemDetails } from '@srbg/contracts'
import { computed, ref } from 'vue'

import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import {
  type FeedContentTypeFilter,
  type FeedContentTypeOption,
  useIntelligenceFeed,
} from '../composables/useIntelligenceFeed'
import { createUuidV7 } from '../utils/uuid-v7'

const contentType = ref<FeedContentTypeFilter>('all')
const contentTypeOptions: readonly FeedContentTypeOption[] = [
  { label: '全部', value: 'all' },
  { label: '规定', value: 'SAFETY_REGULATION' },
  { label: '案例', value: 'SAFETY_CASE' },
]
const fallbackRequestId = createUuidV7()

const { data: feed, error, refresh, status } = await useIntelligenceFeed(
  'all',
  'safety',
  contentType,
)

const problem = computed<ProblemDetails | null>(() => {
  if (!error.value) return null
  const response = error.value.data
  if (
    response
    && typeof response === 'object'
    && 'title' in response
    && 'status' in response
    && 'request_id' in response
  ) {
    return response as ProblemDetails
  }

  const restricted = error.value.statusCode === 403
  return {
    detail: restricted
      ? '该安全案例仅在获授权的审核或核实工作区可见。'
      : '安全情报暂时无法加载，请稍后重试。',
    request_id: fallbackRequestId,
    status: restricted ? 403 : 503,
    title: restricted ? '内容访问受限' : '安全情报暂时不可用',
    type: 'about:blank',
  }
})

function selectContentType(value: FeedContentTypeFilter): void {
  contentType.value = value
}
</script>

<template>
  <IntelligenceFeedPage
    :content-type="contentType"
    title="安全情报"
    eyebrow="安全规定与官方案例"
    description="规定与案例共用同一证据化时间线；R3 内容经人工审核后才展示敏感事实。"
    status-label="R3 门禁启用"
    status-tone="pending"
    empty-title="暂无符合条件的安全情报"
    empty-description="可切换全部、规定或案例；平台不会为无结果生成替代内容。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :problem="problem"
    :content-type-options="contentTypeOptions"
    show-filters
    :show-domain-filter="false"
    initial-domain="safety"
    @content-type-change="selectContentType"
    @retry="refresh"
  >
    <template #notice>
      <p class="safety-page__notice">
        平台内容仅供内部信息参考，不替代正式制度、专业审查和现场安全决策。法规效力、事故原因、责任和伤亡等信息以有权机关原文及人工审核结果为准。
      </p>
    </template>
  </IntelligenceFeedPage>
</template>

<style scoped>
.safety-page__notice {
  margin: 0;
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-ink-700);
  background: var(--color-safetyRegulation-50);
  border-left: 3px solid var(--color-safetyRegulation-500);
  border-radius: var(--radius-sm);
}
</style>
