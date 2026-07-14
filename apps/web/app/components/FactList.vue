<script setup lang="ts">
import type { ConfirmedFact, UnverifiedFact } from '@srbg/contracts'
import { EmptyState, StatusBadge } from '@srbg/ui'

withDefaults(
  defineProps<{
    title: string
    facts: readonly (ConfirmedFact | UnverifiedFact)[]
    variant?: 'confirmed' | 'unverified'
    emptyDescription?: string
  }>(),
  {
    variant: 'confirmed',
    emptyDescription: undefined,
  },
)

const emit = defineEmits<{
  evidence: [itemId: string]
}>()

function formatFactValue(fact: ConfirmedFact): string {
  const value = Array.isArray(fact.value) ? fact.value.join('；') : String(fact.value)
  return fact.unit ? `${value} ${fact.unit}` : value
}

function isConfirmedFact(fact: ConfirmedFact | UnverifiedFact): fact is ConfirmedFact {
  return 'reviewed_at' in fact
}

function factKey(fact: ConfirmedFact | UnverifiedFact): string {
  if (isConfirmedFact(fact)) return `${fact.field}:${fact.claim_id}`
  return `${fact.field}:${fact.claim_id ?? fact.conflict_id ?? fact.source_item_id}`
}
</script>

<template>
  <section class="fact-list" :class="`is-${variant}`" :data-fact-state="variant">
    <header class="fact-list__header">
      <h2>{{ title }}</h2>
      <template v-if="variant === 'confirmed'">
        <StatusBadge tone="info" label="有权机关证据" />
        <StatusBadge tone="verified" label="已人工复核" />
      </template>
      <StatusBadge v-else tone="conflict" label="冲突待核实" />
    </header>

    <dl v-if="facts.length" class="fact-list__items">
      <div v-for="fact in facts" :key="factKey(fact)">
        <dt>{{ fact.label }}</dt>
        <dd v-if="isConfirmedFact(fact)">
          <span>{{ formatFactValue(fact) }}</span>
          <button
            v-if="fact.evidence_ids.length"
            type="button"
            data-testid="fact-evidence-trigger"
            @click="emit('evidence', fact.source_item_id)"
          >
            查看证据（{{ fact.evidence_ids.length }}）
          </button>
        </dd>
        <dd v-else>
          <span class="fact-list__pending-value">{{ fact.display_value ?? '待核实' }}</span>
          <span class="fact-list__reason">{{ fact.reason }}</span>
        </dd>
      </div>
    </dl>

    <EmptyState
      v-else
      :title="variant === 'confirmed' ? '暂无已确认事实' : '当前没有待核实事实'"
      :description="emptyDescription"
      :icon="variant === 'confirmed' ? 'ShieldCheck' : 'WarningCircle'"
    />
  </section>
</template>

<style scoped>
.fact-list {
  display: grid;
  min-width: 0;
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  gap: var(--spacing-4);
}

.fact-list.is-unverified {
  border-color: var(--color-conflict-500);
}

.fact-list__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.fact-list__header h2 {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-lg);
}

.fact-list__items {
  display: grid;
  margin: 0;
  gap: var(--spacing-3);
}

.fact-list__items > div {
  display: grid;
  grid-template-columns: minmax(9rem, 0.35fr) minmax(0, 1fr);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--color-border);
  gap: var(--spacing-3);
}

.fact-list__items dt {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.fact-list__items dd {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: start;
  justify-content: space-between;
  margin: 0;
  color: var(--color-ink-900);
  gap: var(--spacing-2) var(--spacing-4);
}

.fact-list__items button {
  min-height: var(--spacing-9);
  padding: var(--spacing-1) var(--spacing-3);
  color: var(--color-brand-700);
  font: inherit;
  font-weight: var(--font-weight-semibold);
  background: transparent;
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.fact-list__pending-value {
  color: var(--color-conflict-700);
  font-weight: var(--font-weight-semibold);
}

.fact-list__reason {
  flex: 1 1 20rem;
  color: var(--color-ink-600);
}

@media (max-width: 47.999rem) {
  .fact-list {
    padding: var(--spacing-4);
  }

  .fact-list__items > div {
    grid-template-columns: 1fr;
    gap: var(--spacing-1);
  }
}
</style>
