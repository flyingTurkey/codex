<script setup lang="ts">
import type { FeedPage, ProblemDetails } from '@srbg/contracts'
import type { AppIconName, StatusBadgeTone } from '@srbg/ui'
import { EmptyState, PageHeader, ProblemNotice, Skeleton, StatusBadge } from '@srbg/ui'
import { computed, ref, watch } from 'vue'

import type {
  FeedContentTypeFilter,
  FeedContentTypeOption,
} from '../composables/useIntelligenceFeed'
import { createUuidV7 } from '../utils/uuid-v7'
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
    loadingLabel?: string
    problem?: ProblemDetails | null
    showFilters?: boolean
    showDomainFilter?: boolean
    initialDomain?: 'all' | 'safety' | 'digital'
    contentType?: FeedContentTypeFilter
    contentTypeOptions?: readonly FeedContentTypeOption[]
    showDigitalFilters?: boolean
    showPaperFilters?: boolean
    showProductFilters?: boolean
    engineeringDomain?: string
    scenario?: string
    maturity?: string
    sourceNature?: string
    paperType?: string
    technologyTag?: string
    accessLevel?: string
    publicationYear?: string
    productKind?: string
    evidenceLevel?: string
    deploymentMode?: string
    loadingMore?: boolean
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
    loadingLabel: '正在加载情报',
    problem: null,
    showFilters: false,
    showDomainFilter: true,
    initialDomain: 'all',
    contentType: 'all',
    contentTypeOptions: () => [
      { label: '全部类型', value: 'all' },
      { label: '安全规定', value: 'SAFETY_REGULATION' },
    ],
    showDigitalFilters: false,
    showPaperFilters: false,
    showProductFilters: false,
    engineeringDomain: 'all',
    scenario: 'all',
    maturity: 'all',
    sourceNature: 'all',
    paperType: 'all',
    technologyTag: 'all',
    accessLevel: 'all',
    publicationYear: 'all',
    productKind: 'all',
    evidenceLevel: 'all',
    deploymentMode: 'all',
    loadingMore: false,
  },
)

const emit = defineEmits<{
  'content-type-change': [value: FeedContentTypeFilter]
  retry: []
  'update:contentType': [value: FeedContentTypeFilter]
  'update:engineeringDomain': [value: string]
  'update:scenario': [value: string]
  'update:maturity': [value: string]
  'update:sourceNature': [value: string]
  'update:paperType': [value: string]
  'update:technologyTag': [value: string]
  'update:accessLevel': [value: string]
  'update:publicationYear': [value: string]
  'update:productKind': [value: string]
  'update:evidenceLevel': [value: string]
  'update:deploymentMode': [value: string]
  'load-more': []
}>()

const selectedDomain = ref(props.initialDomain)
const internalContentType = ref<FeedContentTypeFilter>(props.contentType)
watch(
  () => props.contentType,
  (value) => {
    internalContentType.value = value
  },
)
const selectedType = computed({
  get: () => internalContentType.value,
  set: (value: FeedContentTypeFilter) => {
    internalContentType.value = value
    emit('update:contentType', value)
    emit('content-type-change', value)
  },
})
const suppressedIds = ref<string[]>([])
const pendingSuppressionId = ref<string | null>(null)
const suppressing = ref(false)
const suppressionMessage = ref<string | null>(null)
const suppressionProblem = ref<string | null>(null)
const visibleItems = computed(() => (props.feed?.items ?? []).filter(
  item => !suppressedIds.value.includes(item.id),
))

function requestSuppression(itemId: string): void {
  pendingSuppressionId.value = itemId
  suppressionMessage.value = null
  suppressionProblem.value = null
}

async function confirmSuppression(): Promise<void> {
  const eventId = pendingSuppressionId.value
  if (!eventId || suppressing.value) return
  suppressing.value = true
  try {
    await $fetch('/api/v2/owner/suppressions', {
      method: 'POST',
      headers: { 'Idempotency-Key': createUuidV7() },
      body: {
        action: 'ACTIVATE',
        scope: 'EVENT',
        target_key: eventId,
        feedback_reason: 'OWNER_PREFERENCE',
      },
      retry: 0,
      timeout: 5_000,
    })
    suppressedIds.value = [...suppressedIds.value, eventId]
    pendingSuppressionId.value = null
    suppressionMessage.value = '已隐藏该情报；可在“Feed 偏好”中撤销。'
  }
  catch {
    suppressionProblem.value = '隐藏操作失败，服务端内容未改变，请稍后重试。'
  }
  finally {
    suppressing.value = false
  }
}
</script>

<template>
  <section class="intelligence-feed-page">
    <div v-if="$slots['before-header']" class="intelligence-feed-page__before-header">
      <slot name="before-header" />
    </div>
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
      :content-type-options="contentTypeOptions"
      :show-domain="showDomainFilter"
      :show-digital-filters="showDigitalFilters"
      :show-paper-filters="showPaperFilters"
      :show-product-filters="showProductFilters"
      :engineering-domain="engineeringDomain"
      :scenario="scenario"
      :maturity="maturity"
      :source-nature="sourceNature"
      :paper-type="paperType"
      :technology-tag="technologyTag"
      :access-level="accessLevel"
      :publication-year="publicationYear"
      :product-kind="productKind"
      :evidence-level="evidenceLevel"
      :deployment-mode="deploymentMode"
      @update:engineering-domain="emit('update:engineeringDomain', $event)"
      @update:scenario="emit('update:scenario', $event)"
      @update:maturity="emit('update:maturity', $event)"
      @update:source-nature="emit('update:sourceNature', $event)"
      @update:paper-type="emit('update:paperType', $event)"
      @update:technology-tag="emit('update:technologyTag', $event)"
      @update:access-level="emit('update:accessLevel', $event)"
      @update:publication-year="emit('update:publicationYear', $event)"
      @update:product-kind="emit('update:productKind', $event)"
      @update:evidence-level="emit('update:evidenceLevel', $event)"
      @update:deployment-mode="emit('update:deploymentMode', $event)"
    />

    <div class="intelligence-feed-page__content">
      <section
        v-if="pendingSuppressionId"
        role="alertdialog"
        aria-labelledby="feed-suppression-confirm-title"
        class="intelligence-feed-page__suppression-confirm"
      >
        <strong id="feed-suppression-confirm-title">确认隐藏这条情报？</strong>
        <p>只影响 Feed 展示，不会删除原文、证据、claims 或历史记录。</p>
        <div>
          <button type="button" :disabled="suppressing" @click="confirmSuppression">
            {{ suppressing ? '正在隐藏…' : '确认隐藏' }}
          </button>
          <button type="button" :disabled="suppressing" @click="pendingSuppressionId = null">
            取消
          </button>
        </div>
      </section>
      <p v-if="suppressionMessage" role="status">{{ suppressionMessage }}</p>
      <p v-if="suppressionProblem" role="alert">{{ suppressionProblem }}</p>
      <slot v-if="$slots.default" />
      <Skeleton
        v-else-if="loading"
        class="intelligence-feed-page__loading"
        :lines="5"
        :label="loadingLabel"
      />
      <ProblemNotice
        v-else-if="problem"
        :problem="problem"
        retry-label="重新加载"
        @retry="emit('retry')"
      />
      <template v-else-if="visibleItems.length">
        <TimelineFeed :items="visibleItems" @suppress="requestSuppression" />
        <button
          v-if="feed?.next_cursor"
          type="button"
          class="intelligence-feed-page__more"
          :disabled="loadingMore"
          @click="emit('load-more')"
        >
          {{ loadingMore ? '正在加载…' : '加载更多' }}
        </button>
      </template>
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

.intelligence-feed-page__feed-notice {
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-ink-700);
  background: var(--color-brand-50);
  border: 1px solid var(--color-brand-200);
  border-radius: var(--radius-sm);
}

.intelligence-feed-page__loading {
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.intelligence-feed-page__suppression-confirm {
  display: grid;
  padding: var(--spacing-4);
  background: var(--color-reviewPending-50);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-md);
  gap: var(--spacing-2);
}

.intelligence-feed-page__suppression-confirm p { margin: 0; }
.intelligence-feed-page__suppression-confirm div { display: flex; flex-wrap: wrap; gap: var(--spacing-2); }
.intelligence-feed-page__suppression-confirm button { min-height: 2.75rem; }

.intelligence-feed-page__more {
  display: block;
  min-width: 8rem;
  margin: var(--spacing-5) auto 0;
  padding: var(--spacing-2) var(--spacing-4);
  color: var(--color-brand-700);
  font-weight: var(--font-weight-semibold);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

@media (max-width: 47.999rem) {
  .intelligence-feed-page {
    gap: var(--spacing-4);
  }
}
</style>
