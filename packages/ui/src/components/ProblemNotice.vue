<script setup lang="ts">
import type { ProblemDetails } from '@srbg/contracts'

import AppIcon from './AppIcon.vue'

withDefaults(
  defineProps<{
    problem: ProblemDetails
    retryLabel?: string
  }>(),
  {
    retryLabel: undefined,
  },
)

defineEmits<{
  retry: []
}>()
</script>

<template>
  <section class="srbg-problem-notice" role="alert">
    <AppIcon class="srbg-problem-notice__icon" name="WarningCircle" :size="24" />
    <div class="srbg-problem-notice__copy">
      <h2>{{ problem.title }}</h2>
      <p v-if="problem.detail">{{ problem.detail }}</p>
      <p class="srbg-problem-notice__request">请求编号：{{ problem.request_id }}</p>
    </div>
    <button
      v-if="retryLabel"
      class="srbg-problem-notice__retry"
      type="button"
      @click="$emit('retry')"
    >
      <AppIcon name="RefreshDouble" />
      {{ retryLabel }}
    </button>
  </section>
</template>

<style scoped>
.srbg-problem-notice {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
  border: 1px solid currentColor;
  border-radius: var(--radius-md);
}

.srbg-problem-notice__icon {
  margin-top: var(--spacing-1);
}

.srbg-problem-notice__copy {
  display: grid;
  gap: var(--spacing-1);
}

.srbg-problem-notice h2,
.srbg-problem-notice p {
  margin: 0;
}

.srbg-problem-notice h2 {
  font-size: var(--text-base);
  font-weight: var(--font-weight-semibold);
  line-height: var(--srbg-font-line-height-title);
}

.srbg-problem-notice p {
  font-size: var(--text-base);
  line-height: var(--srbg-font-line-height-body);
}

.srbg-problem-notice__request {
  font-family: var(--font-mono);
  font-size: var(--text-xs) !important;
}

.srbg-problem-notice__retry {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  min-height: var(--spacing-9);
  padding: 0 var(--spacing-3);
  color: var(--color-conflict-700);
  font: inherit;
  font-weight: var(--font-weight-semibold);
  background: var(--color-surface);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.srbg-problem-notice__retry:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

@media (max-width: 39.999rem) {
  .srbg-problem-notice {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .srbg-problem-notice__retry {
    grid-column: 2;
    width: fit-content;
  }
}
</style>
