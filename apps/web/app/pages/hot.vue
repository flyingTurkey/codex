<script setup lang="ts">
import type { FeedPageV2 } from '@srbg/contracts'
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { toLegacyFeed } from '../composables/useIntelligenceFeed'

const result = await useFetch<FeedPageV2>('/api/v2/hotspots', { server: false, retry: 0, timeout: 5_000 })
const feed = computed(() => result.data.value ? toLegacyFeed(result.data.value) : null)
</script>

<template>
  <IntelligenceFeedPage
    title="热点榜单"
    eyebrow="永久授予记录"
    description="展示 7 天独立信源或权威一手来源触发的热点理由；数值总分不对普通页面展示。"
    empty-title="暂无已授予热点"
    empty-description="热点需要满足独立来源或权威一手来源门禁。"
    :feed="feed"
    :loading="result.status.value === 'idle' || result.status.value === 'pending'"
    @retry="result.refresh"
  />
</template>
