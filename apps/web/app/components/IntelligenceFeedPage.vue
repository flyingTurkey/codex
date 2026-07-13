<script setup lang="ts">
import type { AppIconName, StatusBadgeTone } from '@srbg/ui'
import { EmptyState, PageHeader, StatusBadge } from '@srbg/ui'

withDefaults(
  defineProps<{
    title: string
    eyebrow?: string
    description?: string
    statusLabel?: string
    statusTone?: StatusBadgeTone
    emptyTitle: string
    emptyDescription?: string
    emptyIcon?: AppIconName
  }>(),
  {
    eyebrow: undefined,
    description: undefined,
    statusLabel: undefined,
    statusTone: 'info',
    emptyDescription: undefined,
    emptyIcon: 'EmptyPage',
  },
)
</script>

<template>
  <section class="intelligence-feed-page">
    <PageHeader :title="title" :eyebrow="eyebrow" :description="description">
      <template v-if="$slots.actions" #actions>
        <slot name="actions" />
      </template>
    </PageHeader>

    <div
      v-if="statusLabel || $slots['status-detail']"
      class="intelligence-feed-page__status"
      aria-label="页面状态"
    >
      <StatusBadge v-if="statusLabel" :tone="statusTone" :label="statusLabel" />
      <slot name="status-detail" />
    </div>

    <div v-if="$slots.notice" class="intelligence-feed-page__notice">
      <slot name="notice" />
    </div>

    <div class="intelligence-feed-page__content">
      <slot>
        <slot name="empty">
          <EmptyState :title="emptyTitle" :description="emptyDescription" :icon="emptyIcon" />
        </slot>
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

.intelligence-feed-page__status {
  display: flex;
  min-height: var(--spacing-10);
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-3);
  padding-block: var(--spacing-2);
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: var(--srbg-font-line-height-metadata);
  border-block: 1px solid var(--color-border);
}

.intelligence-feed-page__notice,
.intelligence-feed-page__content {
  min-width: 0;
}

@media (max-width: 47.999rem) {
  .intelligence-feed-page {
    gap: var(--spacing-4);
  }
}
</style>
