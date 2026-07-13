<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { AppIconName } from '../icons'

withDefaults(
  defineProps<{
    title: string
    description?: string
    icon?: AppIconName
  }>(),
  {
    description: undefined,
    icon: 'EmptyPage',
  },
)
</script>

<template>
  <section class="srbg-empty-state" role="status">
    <AppIcon class="srbg-empty-state__icon" :name="icon" :size="32" />
    <h2 class="srbg-empty-state__title">{{ title }}</h2>
    <p v-if="description" class="srbg-empty-state__description">{{ description }}</p>
    <div v-if="$slots.actions" class="srbg-empty-state__actions">
      <slot name="actions" />
    </div>
  </section>
</template>

<style scoped>
.srbg-empty-state {
  display: grid;
  place-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-12) var(--spacing-6);
  color: var(--color-ink-600);
  text-align: center;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.srbg-empty-state__icon {
  color: var(--color-brand-600);
}

.srbg-empty-state__title,
.srbg-empty-state__description {
  margin: 0;
}

.srbg-empty-state__title {
  color: var(--color-ink-900);
  font-size: var(--text-lg);
  font-weight: var(--font-weight-semibold);
  line-height: var(--srbg-font-line-height-title);
}

.srbg-empty-state__description {
  max-width: var(--srbg-layout-detail-main);
  font-size: var(--text-base);
  line-height: var(--srbg-font-line-height-body);
}

.srbg-empty-state__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-1);
}
</style>
