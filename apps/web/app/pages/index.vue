<script setup lang="ts">
import type { ProblemDetails, VersionResponse } from '@srbg/contracts'

import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import GlobalSearch from '../components/GlobalSearch.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'
import { createUuidV7 } from '../utils/uuid-v7'

const { data: feed, status, loadMore, loadingMore } = useIntelligenceFeed('selected')
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
const freshnessLabel = computed(() => {
  if (feed.value?.freshness === 'delayed') return '来源延迟'
  if (feed.value?.freshness === 'partial') return '部分来源异常'
  return '数据已更新'
})

function search(value: string): void {
  void navigateTo({ path: '/search', query: { q: value } })
}
</script>

<template>
  <IntelligenceFeedPage
    title="今日精选"
    eyebrow="精选发布"
    description="只有通过审核与发布门禁并进入精选投影的内容才会出现在这里。"
    :status-label="freshnessLabel"
    :status-tone="feed?.freshness === 'fresh' ? 'healthy' : 'pending'"
    empty-title="暂无精选内容"
    empty-description="当前没有同时通过审核、证据与发布门禁并进入精选投影的内容。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :updated-at="feed?.generated_at ?? versionCheckedAt ?? undefined"
    :loading-more="loadingMore"
    @load-more="loadMore"
  >
    <template #actions>
      <GlobalSearch @search="search" />
    </template>
    <template #notice>
      <p v-if="problem" role="alert">{{ problem.title }}：{{ problem.detail }}</p>
      <section v-else class="today-summary" aria-label="今日重点与数据状态">
        <div><strong>{{ feed?.items.length ?? 0 }}</strong><span>今日重点</span></div>
        <div><strong>{{ freshnessLabel }}</strong><span>采集与投影状态</span></div>
        <div><strong>{{ feed?.fingerprint ?? '等待数据' }}</strong><span>内容指纹</span></div>
      </section>
    </template>
    <template #status-detail>
      <span v-if="version">API {{ version.api_version }} · Schema {{ version.content_schema_version }}</span>
    </template>
  </IntelligenceFeedPage>
</template>

<style scoped>
.today-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  gap: var(--spacing-4);
}
.today-summary div { display: grid; gap: var(--spacing-1); min-width: 0; }
.today-summary strong { color: var(--color-ink-900); overflow-wrap: anywhere; }
.today-summary span { color: var(--color-ink-600); font-size: var(--text-xs); }
@media (max-width: 47.999rem) { .today-summary { grid-template-columns: 1fr; } }
</style>
