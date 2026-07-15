<script setup lang="ts">
import type { CollectionSummary, FeedPage, ProblemDetails } from '@srbg/contracts'
import { computed, ref } from 'vue'

import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { createUuidV7 } from '../utils/uuid-v7'

const selectedCollection = ref<string>('')
const { data: collections, refresh: refreshCollections } = await useFetch<CollectionSummary[]>('/api/v1/collections', { server: false, retry: 0 })
const { data: feed, error, refresh, status } = await useFetch<FeedPage>('/api/v1/saved-items', {
  query: computed(() => ({ collection_id: selectedCollection.value || undefined })),
  server: false, retry: 0, timeout: 5_000,
})
const problem = computed(() => error.value?.data as ProblemDetails ?? null)
const newCollectionName = ref('')
const loadingMore = ref(false)

async function createCollection(): Promise<void> {
  const name = newCollectionName.value.trim()
  if (!name) return
  await $fetch('/api/v1/collections', {
    method: 'POST', body: { name }, headers: { 'Idempotency-Key': createUuidV7() },
  })
  newCollectionName.value = ''
  await refreshCollections()
}

async function loadMore(): Promise<void> {
  const current = feed.value
  if (!current?.next_cursor || loadingMore.value) return
  loadingMore.value = true
  try {
    const next = await $fetch<FeedPage>('/api/v1/saved-items', {
      query: {
        collection_id: selectedCollection.value || undefined,
        cursor: current.next_cursor,
      },
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
    title="收藏与专题"
    eyebrow="仅自己可见"
    description="收藏读取时会重新应用当前 ACL；撤回内容只保留文字状态，不展示旧摘要。"
    empty-title="还没有收藏情报"
    empty-description="可从信息流、搜索或详情页收藏情报。"
    :feed="feed"
    :loading="status === 'idle' || status === 'pending'"
    :loading-more="loadingMore"
    :problem="problem"
    @load-more="loadMore"
    @retry="refresh"
  >
    <template #actions>
      <div class="saved-controls">
        <label>专题<select v-model="selectedCollection"><option value="">全部收藏</option><option v-for="collection in collections ?? []" :key="collection.id" :value="collection.id">{{ collection.name }}（{{ collection.item_count }}）</option></select></label>
        <form @submit.prevent="createCollection"><label>新建私有专题<input v-model="newCollectionName" maxlength="100"></label><button type="submit">新建</button></form>
      </div>
    </template>
  </IntelligenceFeedPage>
</template>

<style scoped>
.saved-controls,
.saved-controls form,
.saved-controls label { display: flex; flex-wrap: wrap; align-items: end; gap: var(--spacing-2); }
.saved-controls label { color: var(--color-ink-700); font-size: var(--text-sm); }
.saved-controls select,
.saved-controls input,
.saved-controls button { min-height: 2.5rem; padding: var(--spacing-2); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); background: var(--color-surface); }
</style>
