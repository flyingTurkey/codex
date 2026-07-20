<script setup lang="ts">
import { ref, useId } from 'vue'

const props = withDefaults(defineProps<{ initialQuery?: string }>(), { initialQuery: '' })
const emit = defineEmits<{ search: [query: string] }>()
const query = ref(props.initialQuery)
const searchId = useId()
const inputId = `${searchId}-input`
const labelId = `${searchId}-label`

function submit(): void {
  const normalized = query.value.trim()
  if (normalized) emit('search', normalized)
}
</script>

<template>
  <form class="global-search" role="search" :aria-labelledby="labelId" @submit.prevent="submit">
    <label :id="labelId" :for="inputId">搜索行业情报</label>
    <div class="global-search__controls">
      <input
        :id="inputId"
        v-model="query"
        name="q"
        type="search"
        maxlength="200"
        required
        placeholder="搜索隧道+监测预警+四川，或输入文号、标准号、DOI"
        autocomplete="off"
      >
      <button type="submit">搜索</button>
    </div>
    <p>“+”表示同时包含；精确编号结果始终优先。</p>
  </form>
</template>

<style scoped>
.global-search {
  display: grid;
  gap: var(--spacing-2);
}

.global-search label {
  color: var(--color-ink-800);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.global-search__controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--spacing-2);
}

.global-search input,
.global-search button {
  min-height: 2.75rem;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.global-search input { background: var(--color-surface); }
.global-search button {
  color: var(--color-surface);
  font-weight: var(--font-weight-semibold);
  background: var(--color-brand-700);
  cursor: pointer;
}

.global-search p {
  margin: 0;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

@media (max-width: 40rem) {
  .global-search__controls { grid-template-columns: 1fr; }
}
</style>
