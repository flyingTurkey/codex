<script setup lang="ts">
import type { FeedPage } from '@srbg/contracts'
import type { AppIconName, StatusBadgeTone } from '@srbg/ui'
import { EmptyState, PageHeader, StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

import FilterPanel from './FilterPanel.vue'
import TimelineFeed from './TimelineFeed.vue'

const props = withDefaults(
  defineProps<{
    title: string
    eyebrow?: string
    description?: string
    statusLabel?: string
    statusTone?: StatusBadgeTone
    updatedAt?: string
    updatedLabel?: string
    emptyTitle: string
    emptyDescription?: string
    emptyIcon?: AppIconName
    feed?: FeedPage | null
    loading?: boolean
    showFilters?: boolean
    initialDomain?: 'all' | 'safety' | 'digital'
  }>(),
  {
    eyebrow: undefined,
    description: undefined,
    statusLabel: undefined,
    statusTone: 'info',
    updatedAt: undefined,
    updatedLabel: '更新时间',
    emptyDescription: undefined,
    emptyIcon: 'EmptyPage',
    feed: null,
    loading: false,
    showFilters: false,
    initialDomain: 'all',
  },
)

const selectedDomain = ref(props.initialDomain)
const selectedType = ref<'all' | 'SAFETY_REGULATION'>('all')
const visibleItems = computed(() =>
  (props.feed?.items ?? []).filter((item) => {
    const domainMatches =
      selectedDomain.value === 'all' || item.domain.toLowerCase() === selectedDomain.value
    const typeMatches = selectedType.value === 'all' || item.content_type === selectedType.value
    return domainMatches && typeMatches
  }),
)
</script>

<template>
  <section class="intelligence-feed-page">
    <PageHeader
      :title="title"
      :eyebrow="eyebrow"
      :description="description"
      :updated-at="updatedAt"
      :updated-label="updatedLabel"
    >
      <template v-if="statusLabel || $slots['status-detail']" #status>
        <StatusBadge v-if="statusLabel" :tone="statusTone" :label="statusLabel" />
        <slot name="status-detail" />
      </template>
      <template v-if="$slots.actions" #actions>
        <slot name="actions" />
      </template>
    </PageHeader>

    <div v-if="$slots.notice" class="intelligence-feed-page__notice">
      <slot name="notice" />
    </div>

    <div
      v-for="notice in feed?.notices ?? []"
      :key="notice.code"
      class="intelligence-feed-page__feed-notice"
      :data-level="notice.level"
      role="status"
    >
      {{ notice.message }}
    </div>

    <FilterPanel
      v-if="showFilters"
      v-model:domain="selectedDomain"
      v-model:content-type="selectedType"
    />

    <div class="intelligence-feed-page__content">
      <slot v-if="$slots.default" />
      <div v-else-if="loading" class="intelligence-feed-page__loading" role="status">
        正在加载情报…
      </div>
      <TimelineFeed v-else-if="visibleItems.length" :items="visibleItems" />
      <slot v-else name="empty">
        <EmptyState :title="emptyTitle" :description="emptyDescription" :icon="emptyIcon" />
      </slot>
    </div>
  </section>
</template>

<style scoped>
.intelligence-feed-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.intelligence-feed-page__notice,
.intelligence-feed-page__content {
  min-width: 0;
}

.intelligence-feed-page__feed-notice,
.intelligence-feed-page__loading {
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-ink-700);
  background: var(--color-brand-50);
  border: 1px solid var(--color-brand-200);
  border-radius: var(--radius-sm);
}

@media (max-width: 47.999rem) {
  .intelligence-feed-page {
    gap: var(--spacing-4);
  }
}
</style>
