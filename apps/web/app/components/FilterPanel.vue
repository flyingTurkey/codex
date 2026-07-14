<script setup lang="ts">
withDefaults(
  defineProps<{
    domain?: 'all' | 'safety' | 'digital'
    contentType?: 'all' | 'SAFETY_REGULATION'
  }>(),
  { domain: 'all', contentType: 'all' },
)

const emit = defineEmits<{
  'update:domain': [value: 'all' | 'safety' | 'digital']
  'update:contentType': [value: 'all' | 'SAFETY_REGULATION']
}>()
</script>

<template>
  <form class="filter-panel" aria-label="情报筛选" @submit.prevent>
    <label>
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
    <label>
      内容类型
      <select
        :value="contentType"
        @change="emit('update:contentType', ($event.target as HTMLSelectElement).value as 'all' | 'SAFETY_REGULATION')"
      >
        <option value="all">全部类型</option>
        <option value="SAFETY_REGULATION">安全规定</option>
      </select>
    </label>
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

.filter-panel select {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-800);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}
</style>
