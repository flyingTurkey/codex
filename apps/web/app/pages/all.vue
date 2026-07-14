<script setup lang="ts">
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'

const { data: feed, status } = await useIntelligenceFeed('all')
</script>

<template>
  <IntelligenceFeedPage
    title="全部动态"
    eyebrow="可见情报投影"
    description="按上海时区归组展示自动发现与已发布内容。待审核 R3 内容仅显示安全白名单字段。"
    status-label="实时数据"
    status-tone="info"
    empty-title="暂无可见情报"
    empty-description="来源发现新内容后会出现在这里。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    show-filters
  />
</template>
