<script setup lang="ts">
import { ref } from 'vue'

import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import type {
  FeedContentTypeFilter,
  FeedContentTypeOption,
} from '../composables/useIntelligenceFeed'
import { useIntelligenceFeed } from '../composables/useIntelligenceFeed'

const contentType = ref<FeedContentTypeFilter>('all')
const contentTypeOptions: readonly FeedContentTypeOption[] = [
  { label: '全部类型', value: 'all' },
  { label: '安全规定', value: 'SAFETY_REGULATION' },
  { label: '安全案例', value: 'SAFETY_CASE' },
  { label: '数字化案例', value: 'DIGITAL_CASE' },
  { label: '期刊论文', value: 'JOURNAL_PAPER' },
  { label: '软件产品', value: 'SOFTWARE_PRODUCT' },
  { label: '物联网产品', value: 'IOT_PRODUCT' },
  { label: '低空设备', value: 'LOW_ALTITUDE_EQUIPMENT' },
  { label: 'AI 设备', value: 'AI_EQUIPMENT' },
]
const { data: feed, status, loadMore, loadingMore } = useIntelligenceFeed(
  'all',
  undefined,
  contentType,
)
</script>

<template>
  <IntelligenceFeedPage
    v-model:content-type="contentType"
    title="全部动态"
    eyebrow="可见情报投影"
    description="按上海时区归组展示自动发现与已发布内容。待审核 R3 内容仅显示安全白名单字段。"
    status-label="实时数据"
    status-tone="info"
    empty-title="暂无可见情报"
    empty-description="来源发现新内容后会出现在这里。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :content-type-options="contentTypeOptions"
    show-filters
    :loading-more="loadingMore"
    @load-more="loadMore"
  />
</template>
