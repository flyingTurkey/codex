<script setup lang="ts">
import type { ItemSummary } from '@srbg/contracts'
import { computed } from 'vue'

const props = defineProps<{ item: ItemSummary }>()

const emit = defineEmits<{
  evidence: [itemId: string]
}>()

const shanghaiDateTime = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Shanghai',
})

function formatDate(value: string | null): string {
  return value ? shanghaiDateTime.format(new Date(value)) : '发布时间待补充'
}

const documentStateLabels = {
  UPDATED: '已更新',
  RE_REVIEW_PENDING: '待复核',
  WITHDRAWN: '已撤回',
  SOURCE_UNAVAILABLE: '原文失效',
} as const

const documentStates = computed(() => props.item.document_states ?? [])
</script>

<template>
  <article class="intelligence-card" :data-review-status="item.review_status">
    <div class="intelligence-card__meta">
      <span class="intelligence-card__type">安全规定</span>
      <span
        v-for="state in documentStates"
        :key="state"
        class="intelligence-card__badge is-document-state"
        :data-document-state="state"
      >
        {{ documentStateLabels[state] }}
      </span>
      <span v-if="item.review_status === 'PENDING'" class="intelligence-card__badge is-pending">
        待人工审核
      </span>
      <template v-else>
        <span v-if="item.source_role" class="intelligence-card__badge">
          {{ item.source_role }}
        </span>
        <span class="intelligence-card__badge is-reviewed">已人工复核</span>
      </template>
    </div>

    <h3 class="intelligence-card__title">
      <a :href="`/items/${item.id}`">{{ item.title }}</a>
    </h3>

    <dl class="intelligence-card__source">
      <div>
        <dt>来源</dt>
        <dd>{{ item.source_name }}</dd>
      </div>
      <div>
        <dt>原文发布时间</dt>
        <dd>{{ formatDate(item.source_published_at) }}</dd>
      </div>
    </dl>

    <template v-if="item.publication_revision_id && item.type_summary">
      <dl class="intelligence-card__facts">
        <div>
          <dt>文号</dt>
          <dd>{{ item.type_summary.document_number }}</dd>
        </div>
        <div>
          <dt>发布机关</dt>
          <dd>{{ item.type_summary.issuing_authority }}</dd>
        </div>
        <div>
          <dt>效力状态</dt>
          <dd>
            {{ item.type_summary.regulation_status === 'UNKNOWN' ? '效力状态待核验' : item.type_summary.regulation_status }}
          </dd>
        </div>
      </dl>
    </template>

    <footer class="intelligence-card__footer">
      <a :href="item.original_url" target="_blank" rel="noreferrer">查看官方原文</a>
      <button
        v-if="item.publication_revision_id && item.evidence_status === 'VERIFIED'"
        type="button"
        data-testid="evidence-trigger"
        @click="emit('evidence', item.id)"
      >
        查看证据（{{ item.evidence_count ?? 0 }}）
      </button>
    </footer>
  </article>
</template>

<style scoped>
.intelligence-card {
  display: grid;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.intelligence-card__meta,
.intelligence-card__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.intelligence-card__type,
.intelligence-card__badge {
  padding: var(--spacing-1) var(--spacing-2);
  color: var(--color-ink-700);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-pill);
}

.intelligence-card__badge.is-pending {
  color: var(--color-reviewPending-700);
  background: var(--color-reviewPending-50);
}

.intelligence-card__badge.is-reviewed {
  color: var(--color-verified-700);
  background: var(--color-verified-50);
}

.intelligence-card__badge.is-document-state[data-document-state='UPDATED'] {
  color: var(--color-brand-700);
  background: var(--color-brand-50);
}

.intelligence-card__badge.is-document-state[data-document-state='RE_REVIEW_PENDING'] {
  color: var(--color-reviewPending-700);
  background: var(--color-reviewPending-50);
}

.intelligence-card__badge.is-document-state[data-document-state='WITHDRAWN'],
.intelligence-card__badge.is-document-state[data-document-state='SOURCE_UNAVAILABLE'] {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

.intelligence-card__title {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-xl);
  line-height: var(--srbg-font-line-height-title);
}

.intelligence-card__title a {
  text-decoration: none;
}

.intelligence-card__title a:hover {
  text-decoration: underline;
}

.intelligence-card__source,
.intelligence-card__facts {
  display: grid;
  margin: 0;
  gap: var(--spacing-3);
}

.intelligence-card__source {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.intelligence-card__facts {
  padding: var(--spacing-4);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-md);
}

.intelligence-card dl div {
  min-width: 0;
}

.intelligence-card dt {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.intelligence-card dd {
  margin: var(--spacing-1) 0 0;
  color: var(--color-ink-800);
}

.intelligence-card__footer {
  justify-content: space-between;
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--color-border);
}

.intelligence-card__footer a,
.intelligence-card__footer button {
  color: var(--color-brand-700);
  font-weight: var(--font-weight-semibold);
}

.intelligence-card__footer button {
  padding: var(--spacing-2) var(--spacing-3);
  background: transparent;
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

@media (max-width: 40rem) {
  .intelligence-card {
    padding: var(--spacing-4);
  }

  .intelligence-card__source {
    grid-template-columns: 1fr;
  }
}
</style>
