<script setup lang="ts">
import type { FeedPageV2, ProblemDetails } from '@srbg/contracts'
import GlobalSearch from '../components/GlobalSearch.vue'
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { toLegacyFeed } from '../composables/useIntelligenceFeed'

const route = useRoute()
const query = computed(() => typeof route.query.q === 'string' ? route.query.q : '')
const result = await useFetch<FeedPageV2>('/api/v2/search', {
  query: { q: query }, server: false, immediate: Boolean(query.value), retry: 0, timeout: 5_000,
})
const feed = computed(() => result.data.value ? toLegacyFeed(result.data.value) : null)
const problem = computed(() => result.error.value?.data as ProblemDetails ?? null)
const loadingMore = ref(false)
function search(value: string): void { void navigateTo({ path: '/search', query: { q: value } }) }
async function loadMore(): Promise<void> {
  const current = result.data.value
  if (!current?.next_cursor || loadingMore.value) return
  loadingMore.value = true
  try {
    const next = await $fetch<FeedPageV2>('/api/v2/search', {
      query: { q: query.value, cursor: current.next_cursor },
    })
    result.data.value = { ...next, items: [...current.items, ...next.items] }
  }
  finally { loadingMore.value = false }
}
</script>

<template>
  <IntelligenceFeedPage
    title="搜索"
    eyebrow="证据优先 · AI 低权重辅助召回"
    description="标题、来源、accepted claims 与原文摘录优先；AI 总结仅作带来源说明的辅助召回。"
    empty-title="没有找到匹配情报"
    empty-description="可减少组合词，或核对工程对象和来源名称。"
    :feed="feed"
    :loading="Boolean(query) && (result.status.value === 'idle' || result.status.value === 'pending')"
    :problem="problem"
    :loading-more="loadingMore"
    @load-more="loadMore"
    @retry="result.refresh"
  >
    <template #before-header><GlobalSearch :initial-query="query" @search="search" /></template>
    <template v-if="!query" #empty><GlobalSearch @search="search" /></template>
  </IntelligenceFeedPage>
</template>
