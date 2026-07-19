<script setup lang="ts">
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'

const { data: feed, status, refresh, loadMore, loadingMore } = useIntelligenceFeed('all', 'industry')
</script>

<template>
  <IntelligenceFeedPage
    title="行业热点"
    eyebrow="土木工程行业"
    description="与工程建设、运营和装备直接相关的新进展；热点授予不改变情报主类型。"
    empty-title="暂无行业热点"
    empty-description="当前没有通过相关性与证据门禁的行业热点。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :loading-more="loadingMore"
    @retry="refresh"
    @load-more="loadMore"
  />
</template>
