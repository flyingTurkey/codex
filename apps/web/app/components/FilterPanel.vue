<script setup lang="ts">
import type {
  FeedContentTypeFilter,
  FeedContentTypeOption,
} from '../composables/useIntelligenceFeed'

withDefaults(
  defineProps<{
    domain?: 'all' | 'safety' | 'digital'
    contentType?: FeedContentTypeFilter
    contentTypeOptions?: readonly FeedContentTypeOption[]
    showDomain?: boolean
  }>(),
  {
    domain: 'all',
    contentType: 'all',
    contentTypeOptions: () => [
      { label: '全部类型', value: 'all' },
      { label: '安全规定', value: 'SAFETY_REGULATION' },
    ],
    showDomain: true,
  },
)

const emit = defineEmits<{
  'update:domain': [value: 'all' | 'safety' | 'digital']
  'update:contentType': [value: FeedContentTypeFilter]
}>()
</script>

<template>
  <form class="filter-panel" aria-label="情报筛选" @submit.prevent>
    <label v-if="showDomain">
      频道
      <select
        :value="domain"
        @change="emit('update:domain', ($event.target as HTMLSelectElement).value as 'all' | 'safety' | 'digital')"
      >
        <option value="all">全部</option>
        <option value="safety">安全</option>
        <option value="digital">数字化</option>
      </select>
    </label>
    <fieldset class="filter-panel__types" role="group" aria-label="安全内容类型">
      <legend>内容类型</legend>
      <div class="filter-panel__segments">
        <button
          v-for="option in contentTypeOptions"
          :key="option.value"
          type="button"
          :data-content-type="option.value"
          :aria-pressed="contentType === option.value"
          @click="emit('update:contentType', option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </fieldset>
  </form>
</template>

<style scoped>
.filter-panel {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.filter-panel label {
  display: grid;
  min-width: 10rem;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  gap: var(--spacing-1);
}

.filter-panel__types {
  display: grid;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
  gap: var(--spacing-1);
}

.filter-panel__types legend {
  padding: 0;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.filter-panel__segments {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.filter-panel__segments button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-4);
  color: var(--color-ink-700);
  font: inherit;
  font-weight: var(--font-weight-semibold);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.filter-panel__segments button[aria-pressed='true'] {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}

.filter-panel select {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-800);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

@media (max-width: 39.999rem) {
  .filter-panel,
  .filter-panel label,
  .filter-panel__types {
    width: 100%;
  }

  .filter-panel__segments button {
    flex: 1 1 0;
  }
}
</style>
