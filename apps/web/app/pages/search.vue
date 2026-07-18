<script setup lang="ts">
import type { FeedPage, ProblemDetails } from '@srbg/contracts'
import { computed, ref } from 'vue'

import GlobalSearch from '../components/GlobalSearch.vue'
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'

const route = useRoute()
const query = computed(() => typeof route.query.q === 'string' ? route.query.q : '')
const { data: feed, error, refresh, status } = await useAsyncData<FeedPage | null>(
  'round10-search-feed',
  () => query.value
    ? $fetch<FeedPage>('/api/v1/search', { query: { q: query.value }, timeout: 5_000 })
    : Promise.resolve(null),
  { server: false, watch: [query], default: () => null },
)
const problem = computed(() => error.value?.data as ProblemDetails ?? null)
const loadingMore = ref(false)

function search(value: string): void {
  void navigateTo({ path: '/search', query: { q: value } })
}

async function loadMore(): Promise<void> {
  const current = feed.value
  if (!current?.next_cursor || loadingMore.value) return
  loadingMore.value = true
  try {
    const next = await $fetch<FeedPage>('/api/v1/search', {
      query: { q: query.value, cursor: current.next_cursor },
      timeout: 5_000,
    })
    feed.value = { ...next, items: [...current.items, ...next.items] }
  }
  finally {
    loadingMore.value = false
  }
}
</script>

<template>
  <IntelligenceFeedPage
    title="搜索"
    eyebrow="精确编号优先 · 语义增强可降级"
    description="正文命中只用于召回；列表仍仅显示已接受事实和公开证据。"
    empty-title="没有找到匹配情报"
    empty-description="可减少组合词，或核对文号、标准号和 DOI。"
    :feed="feed"
    :loading="Boolean(query) && (status === 'idle' || status === 'pending')"
    :loading-more="loadingMore"
    :problem="problem"
    @load-more="loadMore"
    @retry="refresh"
  >
    <template #notice>
      <aside class="result-legend" aria-label="搜索结果类型说明">
        <strong>证据事实</strong>来自可定位原文；<strong>AI 判断</strong>已通过验证；
        <strong>未验证 AI</strong>以独立卡片保留；<strong>AI 处理失败</strong>仅显示安全失败原因。
      </aside>
    </template>
    <template #actions>
      <GlobalSearch :initial-query="query" @search="search" />
    </template>
    <template v-if="!query" #empty>
      <GlobalSearch @search="search" />
    </template>
  </IntelligenceFeedPage>
</template>

<style scoped>
.result-legend { padding: var(--spacing-3); color: var(--color-ink-700); background: var(--color-surface-muted); border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
</style>
