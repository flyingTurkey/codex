<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    eyebrow?: string
    description?: string
  }>(),
  {
    eyebrow: undefined,
    description: undefined,
  },
)
</script>

<template>
  <header class="srbg-page-header">
    <div class="srbg-page-header__copy">
      <p v-if="eyebrow" class="srbg-page-header__eyebrow">{{ eyebrow }}</p>
      <h1 class="srbg-page-header__title">{{ title }}</h1>
      <p v-if="description" class="srbg-page-header__description">{{ description }}</p>
      <slot name="meta" />
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
}
</style>
