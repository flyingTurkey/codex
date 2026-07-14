<script setup lang="ts">
import type { EventItem, EventRelationView } from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { EmptyState, StatusBadge } from '@srbg/ui'
import { computed } from 'vue'

const props = defineProps<{
  items: readonly EventItem[]
  relations: readonly EventRelationView[]
}>()

const shanghaiDateTime = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'long',
  timeStyle: 'short',
  timeZone: 'Asia/Shanghai',
})

const itemById = computed(() => new Map(props.items.map((item) => [item.item_id, item])))

const relationPresentations = {
  CORRECTS: { label: '更正前序材料', tone: 'info' },
  FOLLOW_UP: { label: '续报前序材料', tone: 'pending' },
  INVESTIGATES: { label: '调查前序材料', tone: 'verified' },
  PENALIZES: { label: '处罚问责材料', tone: 'verified' },
  RECTIFIES: { label: '整改评估材料', tone: 'info' },
} as const satisfies Record<
  EventRelationView['relation_type'],
  { label: string; tone: StatusBadgeTone }
>

function relationPresentation(relation: EventRelationView['relation_type']): {
  label: string
  tone: StatusBadgeTone
} {
  return relationPresentations[relation]
}

function itemTitle(itemId: string): string {
  return itemById.value.get(itemId)?.title ?? '受限材料'
}

function itemHref(itemId: string): string | null {
  return itemById.value.has(itemId) ? `/items/${itemId}` : null
}

function formatReviewedAt(value: string): string {
  return shanghaiDateTime.format(new Date(value))
}
</script>

<template>
  <section
    class="event-relations"
    aria-labelledby="event-relations-title"
    data-testid="event-relations"
  >
    <h2 id="event-relations-title">已审核事件关系与更正记录</h2>
    <ol v-if="relations.length" class="event-relations__list">
      <li
        v-for="relation in relations"
        :key="relation.id"
        :data-relation-type="relation.relation_type"
        data-testid="event-relation"
      >
        <article>
          <header>
            <StatusBadge
              :label="relationPresentation(relation.relation_type).label"
              :tone="relationPresentation(relation.relation_type).tone"
            />
            <p>
              审核时间
              <time :datetime="relation.reviewed_at">{{ formatReviewedAt(relation.reviewed_at) }}</time>
            </p>
          </header>
          <div class="event-relations__direction">
            <div>
              <span>关系来源</span>
              <a v-if="itemHref(relation.from_item_id)" :href="itemHref(relation.from_item_id) ?? undefined">
                {{ itemTitle(relation.from_item_id) }}
              </a>
              <strong v-else>{{ itemTitle(relation.from_item_id) }}</strong>
            </div>
            <span class="event-relations__arrow" aria-hidden="true">→</span>
            <div>
              <span>关系目标</span>
              <a v-if="itemHref(relation.to_item_id)" :href="itemHref(relation.to_item_id) ?? undefined">
                {{ itemTitle(relation.to_item_id) }}
              </a>
              <strong v-else>{{ itemTitle(relation.to_item_id) }}</strong>
            </div>
          </div>
        </article>
      </li>
    </ol>
    <EmptyState
      v-else
      title="暂无已审核事件关系"
      description="续报、更正、调查、处罚与整改关系经人工审核后会显示在这里。"
      icon="GraphUp"
    />
  </section>
</template>

<style scoped>
.event-relations {
  display: grid;
  min-width: 0;
  gap: var(--spacing-4);
}

.event-relations > h2 {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-xl);
}

.event-relations__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
  gap: var(--spacing-3);
}

.event-relations article {
  display: grid;
  min-width: 0;
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  gap: var(--spacing-3);
}

.event-relations header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.event-relations header p {
  margin: 0;
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.event-relations header time {
  margin-left: var(--spacing-1);
  color: var(--color-ink-700);
  font-weight: var(--font-weight-semibold);
}

.event-relations__direction {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: var(--spacing-3);
}

.event-relations__direction > div {
  display: grid;
  min-width: 0;
  padding: var(--spacing-3);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
  gap: var(--spacing-1);
}

.event-relations__direction div > span {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.event-relations__direction a,
.event-relations__direction strong {
  overflow-wrap: anywhere;
  color: var(--color-ink-900);
  font-weight: var(--font-weight-semibold);
}

.event-relations__direction a {
  text-decoration-color: var(--color-brand-400);
  text-underline-offset: var(--spacing-1);
}

.event-relations__arrow {
  color: var(--color-brand-700);
  font-size: var(--text-xl);
  font-weight: var(--font-weight-semibold);
}

@media (max-width: 39.999rem) {
  .event-relations header {
    align-items: flex-start;
    flex-direction: column;
  }

  .event-relations__direction {
    grid-template-columns: 1fr;
  }

  .event-relations__arrow {
    justify-self: center;
    transform: rotate(90deg);
  }
}
</style>
