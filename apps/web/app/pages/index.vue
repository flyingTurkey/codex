<script setup lang="ts">
import type { DiscoverySettingView, PersonalSourceView, ProblemDetails, VersionResponse } from '@srbg/contracts'

import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import GlobalSearch from '../components/GlobalSearch.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'
import { createUuidV7 } from '../utils/uuid-v7'

const { data: feed, status, loadMore, loadingMore } = useIntelligenceFeed('selected')
const { data: homeSources } = useFetch<PersonalSourceView[]>('/api/v1/sources', {
  server: false,
  default: () => [],
  retry: 0,
  timeout: 5_000,
})
const { data: discoverySetting } = useFetch<DiscoverySettingView>('/api/v1/source-discovery/settings', {
  server: false,
  retry: 0,
  timeout: 5_000,
})
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
const healthySourceCount = computed(() => homeSources.value.filter(source =>
  source.streams?.some(stream => stream.health_status === 'HEALTHY'),
).length)
const sourceHealthLabel = computed(() => homeSources.value.length
  ? `${healthySourceCount.value}/${homeSources.value.length}`
  : '等待数据')

function search(value: string): void {
  void navigateTo({ path: '/search', query: { q: value } })
}
</script>

<template>
  <IntelligenceFeedPage
    title="今日精选"
    eyebrow="个人研究工作台"
    description="个人来源自动采集的题录与证据事实；机器整理和未人工复核状态始终可见。"
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
    <template #before-header>
      <GlobalSearch @search="search" />
    </template>
    <template #notice>
      <p v-if="problem" role="alert">{{ problem.title }}：{{ problem.detail }}</p>
      <section v-else class="today-summary" aria-label="今日重点与数据状态">
        <div><strong>{{ feed?.items.length ?? 0 }}</strong><span>条情报</span></div>
        <div><strong>{{ sourceHealthLabel }}</strong><span>健康来源</span></div>
        <div><strong>{{ freshnessLabel }}</strong><span>采集与投影状态</span></div>
        <div><strong>{{ discoverySetting?.automation_enabled ? '已开启' : '已关闭' }}</strong><span>自动发现</span></div>
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: var(--spacing-3);
  background: linear-gradient(135deg, var(--color-surface) 0%, var(--color-brand-50) 100%);
  border: 1px solid var(--color-brand-200);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}
.today-summary div { display: grid; min-width: 0; padding: var(--spacing-3) var(--spacing-4); gap: var(--spacing-1); }
.today-summary div + div { border-left: 1px solid var(--color-border); }
.today-summary strong { color: var(--color-brand-800); overflow-wrap: anywhere; font-size: var(--text-lg); }
.today-summary span { color: var(--color-ink-600); font-size: var(--text-xs); }
@media (max-width: 63.999rem) { .today-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } .today-summary div:nth-child(3) { border-left: 0; border-top: 1px solid var(--color-border); } .today-summary div:nth-child(4) { border-top: 1px solid var(--color-border); } }
@media (max-width: 47.999rem) { .today-summary { grid-template-columns: 1fr; } .today-summary div + div { border-top: 1px solid var(--color-border); border-left: 0; } }
</style>
