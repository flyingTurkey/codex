<script setup lang="ts">
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'

const { data: feed, status } = await useIntelligenceFeed('all', 'safety')
</script>

<template>
  <IntelligenceFeedPage
    title="安全情报"
    eyebrow="安全规定"
    description="官方来源的新规定先进入 R3 人工审核，审核通过后展示字段证据。"
    status-label="R3 门禁启用"
    status-tone="pending"
    empty-title="暂无安全规定"
    empty-description="固定来源尚未发现新规定。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    show-filters
    initial-domain="safety"
  />
</template>
