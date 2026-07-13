<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    eyebrow?: string
    description?: string
    updatedAt?: string
    updatedLabel?: string
  }>(),
  {
    eyebrow: undefined,
    description: undefined,
    updatedAt: undefined,
    updatedLabel: '更新时间',
  },
)

const shanghaiDateTime = new Intl.DateTimeFormat('zh-CN', {
  day: '2-digit',
  hour: '2-digit',
  hourCycle: 'h23',
  minute: '2-digit',
  month: '2-digit',
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
})

function formatShanghaiDateTime(timestamp: string): string {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return timestamp

  const parts = Object.fromEntries(
    shanghaiDateTime
      .formatToParts(date)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  )

  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`
}

const visibleUpdatedAt = computed(() =>
  props.updatedAt ? formatShanghaiDateTime(props.updatedAt) : undefined,
)
</script>

<template>
  <header class="srbg-page-header">
    <div class="srbg-page-header__copy">
      <p v-if="eyebrow" class="srbg-page-header__eyebrow">{{ eyebrow }}</p>
      <h1 class="srbg-page-header__title">{{ title }}</h1>
      <p v-if="description" class="srbg-page-header__description">{{ description }}</p>
      <slot name="meta" />
      <div
        v-if="updatedAt || $slots.status"
        class="srbg-page-header__meta"
        role="group"
        aria-label="页面状态与更新时间"
      >
        <div v-if="$slots.status" class="srbg-page-header__status">
          <slot name="status" />
        </div>
        <p v-if="updatedAt" class="srbg-page-header__updated-at">
          <span>{{ updatedLabel }}：</span>
          <time :datetime="updatedAt" data-testid="page-updated-at">{{ visibleUpdatedAt }}</time>
        </p>
      </div>
    </div>
    <div v-if="$slots.actions" class="srbg-page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.srbg-page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--spacing-6);
}

.srbg-page-header__copy {
  display: grid;
  flex: 1;
  gap: var(--spacing-1);
  min-width: 0;
}

.srbg-page-header__eyebrow,
.srbg-page-header__description,
.srbg-page-header__title {
  margin: 0;
}

.srbg-page-header__eyebrow {
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  line-height: var(--srbg-font-line-height-metadata);
}

.srbg-page-header__title {
  color: var(--color-ink-900);
  font-size: var(--text-2xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--srbg-font-line-height-heading);
}

.srbg-page-header__description {
  color: var(--color-ink-600);
  font-size: var(--text-base);
  line-height: var(--srbg-font-line-height-body);
}

.srbg-page-header__meta {
  display: flex;
  min-height: var(--spacing-10);
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-3);
  margin-top: var(--spacing-1);
  padding-block: var(--spacing-2);
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: var(--srbg-font-line-height-metadata);
  border-block: 1px solid var(--color-border);
}

.srbg-page-header__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-3);
}

.srbg-page-header__updated-at {
  margin: 0 0 0 auto;
}

.srbg-page-header__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

@media (max-width: 47.999rem) {
  .srbg-page-header {
    align-items: stretch;
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .srbg-page-header__updated-at {
    margin-left: 0;
  }
}
</style>
