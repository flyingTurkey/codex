<script setup lang="ts">
import type { EventItem } from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { EmptyState, StatusBadge } from '@srbg/ui'

defineProps<{
  items: readonly EventItem[]
}>()

const shanghaiDate = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'long',
  timeZone: 'Asia/Shanghai',
})

function formatDate(value: string | null): string {
  return value ? shanghaiDate.format(new Date(value)) : '发布时间待补充'
}

function stagePresentation(stage: EventItem['report_stage']): {
  label: string
  tone: StatusBadgeTone
} {
  switch (stage) {
    case 'INITIAL_REPORT':
      return { label: '初报', tone: 'pending' }
    case 'FOLLOW_UP_REPORT':
      return { label: '续报', tone: 'pending' }
    case 'FINAL_INVESTIGATION':
      return { label: '正式调查', tone: 'verified' }
    case 'ENFORCEMENT':
      return { label: '处罚问责', tone: 'verified' }
    case 'RECTIFICATION':
      return { label: '整改评估', tone: 'info' }
  }
}

function relationLabel(relation: EventItem['relation_type']): string | null {
  if (!relation) return null
  return {
    CORRECTS: '更正前序材料',
    FOLLOW_UP: '续报前序材料',
    INVESTIGATES: '调查该事件',
    PENALIZES: '形成处罚与问责',
    RECTIFIES: '评估整改落实',
  }[relation]
}

function documentStateLabel(state: NonNullable<EventItem['document_states']>[number]): string {
  return {
    RE_REVIEW_PENDING: '更新待复核',
    SOURCE_UNAVAILABLE: '原文失效',
    UPDATED: '原文已更新',
    WITHDRAWN: '已撤回',
  }[state]
}
</script>

<template>
  <section class="event-timeline" aria-labelledby="event-timeline-title">
    <h2 id="event-timeline-title">事件时间线</h2>
    <ol v-if="items.length" class="event-timeline__items">
      <li v-for="item in items" :key="item.item_id" data-testid="event-stage">
        <span class="event-timeline__rail" aria-hidden="true" />
        <article>
          <div class="event-timeline__status">
            <StatusBadge
              :tone="stagePresentation(item.report_stage).tone"
              :label="stagePresentation(item.report_stage).label"
            />
            <span v-if="relationLabel(item.relation_type)" class="event-timeline__relation">
              {{ relationLabel(item.relation_type) }}
            </span>
            <StatusBadge
              v-for="state in item.document_states ?? []"
              :key="state"
              :tone="state === 'WITHDRAWN' || state === 'SOURCE_UNAVAILABLE' ? 'withdrawn' : 'pending'"
              :label="documentStateLabel(state)"
            />
          </div>
          <h3><a :href="`/items/${item.item_id}`">{{ item.title }}</a></h3>
          <dl>
            <div>
              <dt>官方来源</dt>
              <dd>{{ item.source_name }}</dd>
            </div>
            <div>
              <dt>原文发布时间</dt>
              <dd>{{ formatDate(item.source_published_at) }}</dd>
            </div>
            <div>
              <dt>字段证据</dt>
              <dd>{{ item.evidence_count ?? 0 }} 条</dd>
            </div>
          </dl>
          <a class="event-timeline__original" :href="item.original_url" target="_blank" rel="noreferrer">
            查看官方原文
          </a>
        </article>
      </li>
    </ol>
    <EmptyState
      v-else
      title="暂无可见事件阶段"
      description="可能尚未形成已审核关系，或当前账号无权查看受限阶段。"
      icon="Clock"
    />
  </section>
</template>

<style scoped>
.event-timeline {
  display: grid;
  min-width: 0;
  gap: var(--spacing-4);
}

.event-timeline > h2 {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-xl);
}

.event-timeline__items {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
  gap: var(--spacing-4);
}

.event-timeline__items > li {
  position: relative;
  display: grid;
  grid-template-columns: var(--spacing-7) minmax(0, 1fr);
}

.event-timeline__rail {
  position: relative;
}

.event-timeline__rail::before {
  position: absolute;
  top: var(--spacing-2);
  bottom: calc(-1 * var(--spacing-6));
  left: calc(50% - 1px);
  width: 2px;
  content: '';
  background: var(--color-borderStrong);
}

.event-timeline__rail::after {
  position: absolute;
  top: var(--spacing-5);
  left: calc(50% - var(--spacing-2));
  width: var(--spacing-4);
  height: var(--spacing-4);
  content: '';
  background: var(--color-surface);
  border: 3px solid var(--color-safetyCase-500);
  border-radius: var(--radius-pill);
}

.event-timeline__items > li:last-child .event-timeline__rail::before {
  bottom: 50%;
}

.event-timeline article {
  display: grid;
  min-width: 0;
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  gap: var(--spacing-3);
}

.event-timeline__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.event-timeline__relation {
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.event-timeline h3 {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-lg);
}

.event-timeline h3 a {
  text-decoration: none;
}

.event-timeline h3 a:hover {
  text-decoration: underline;
}

.event-timeline dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0;
  gap: var(--spacing-3);
}

.event-timeline dt {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.event-timeline dd {
  margin: var(--spacing-1) 0 0;
  color: var(--color-ink-800);
}

.event-timeline__original {
  width: fit-content;
  color: var(--color-brand-700);
  font-weight: var(--font-weight-semibold);
}

@media (max-width: 47.999rem) {
  .event-timeline__items > li {
    grid-template-columns: var(--spacing-5) minmax(0, 1fr);
  }

  .event-timeline article {
    padding: var(--spacing-4);
  }

  .event-timeline dl {
    grid-template-columns: 1fr;
  }
}
</style>
