<script setup lang="ts">
import type { FeedPage, ItemSummary } from '@srbg/contracts'
import { computed } from 'vue'

import IntelligenceCard from './IntelligenceCard.vue'

const props = defineProps<{ items: FeedPage['items'] }>()

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'long',
  timeZone: 'Asia/Shanghai',
})

const groups = computed(() => {
  const result: Array<{ label: string; items: ItemSummary[] }> = []
  for (const item of props.items) {
    const label = dateFormatter.format(new Date(item.activity_at))
    const current = result.at(-1)
    if (current?.label === label) current.items.push(item)
    else result.push({ label, items: [item] })
  }
  return result
})

async function openEvidence(itemId: string): Promise<void> {
  await navigateTo(`/events/${itemId}`)
}
</script>

<template>
  <div class="timeline-feed">
    <section v-for="group in groups" :key="group.label" class="timeline-feed__group">
      <h2>{{ group.label }}</h2>
      <ol>
        <li v-for="item in group.items" :key="item.signal_id ?? item.id">
          <span class="timeline-feed__marker" aria-hidden="true" />
          <IntelligenceCard :item="item" @evidence="openEvidence" />
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.timeline-feed,
.timeline-feed__group {
  display: grid;
  gap: var(--spacing-4);
}

.timeline-feed__group h2 {
  margin: 0;
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.timeline-feed__group ol {
  display: grid;
  margin: 0;
  padding: 0 0 0 var(--spacing-6);
  list-style: none;
  gap: var(--spacing-4);
  border-left: 1px solid var(--color-borderStrong);
}

.timeline-feed__group li {
  position: relative;
}

.timeline-feed__marker {
  position: absolute;
  top: var(--spacing-6);
  left: calc(-1 * var(--spacing-6) - 0.3rem);
  width: 0.6rem;
  height: 0.6rem;
  background: var(--color-brand-500);
  border: 2px solid var(--color-canvas);
  border-radius: var(--radius-pill);
}
</style>
