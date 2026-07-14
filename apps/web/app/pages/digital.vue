<script setup lang="ts">
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'

const { data: feed, status } = await useIntelligenceFeed('all', 'digital')
</script>

<template>
  <IntelligenceFeedPage
    title="数字化"
    eyebrow="数字化情报"
    description="数字化内容不在本轮交付范围。"
    status-label="后续轮次接入"
    status-tone="info"
    empty-title="暂无数字化情报"
    empty-description="本轮仅接入首个安全规定 HTML 来源。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    initial-domain="digital"
  />
</template>
