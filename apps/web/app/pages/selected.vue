<script setup lang="ts">
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'

const { data: feed, status, loadMore, loadingMore } = useIntelligenceFeed('selected')
</script>

<template>
  <IntelligenceFeedPage
    title="今日精选"
    eyebrow="精选发布"
    description="只有通过真实评分与发布门禁的内容才会进入精选。"
    status-label="发布门禁已应用"
    status-tone="healthy"
    empty-title="暂无精选内容"
    empty-description="第 08 轮前缺少真实评分的内容不会进入精选，也不会展示演示分数。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :loading-more="loadingMore"
    @load-more="loadMore"
  />
</template>
