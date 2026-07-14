<script setup lang="ts">
import type {
  ItemSummary,
  SafetyCaseTypeSummary,
  SafetyRegulationTypeSummary,
} from '@srbg/contracts'
import type { StatusBadgeTone } from '@srbg/ui'
import { StatusBadge } from '@srbg/ui'
import { computed } from 'vue'

import { safetyEngineeringLabel, safetyHazardLabel } from '../utils/safety-case-labels'

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

const documentStates = computed(() => {
  const states = [...(props.item.document_states ?? [])]
  if (props.item.publication_status === 'WITHDRAWN' && !states.includes('WITHDRAWN')) {
    states.push('WITHDRAWN')
  }
  return states
})
const isWithdrawn = computed(() => documentStates.value.includes('WITHDRAWN'))
const originalLinkLabel = computed(() => {
  if (isWithdrawn.value) return '查看撤回与存档信息'
  if (documentStates.value.includes('SOURCE_UNAVAILABLE')) return '原文失效，查看存档信息'
  return '查看官方原文'
})

const safetyCaseSummary = computed<SafetyCaseTypeSummary | null>(() => {
  const summary = props.item.type_summary
  return summary?.kind === 'SAFETY_CASE' ? summary : null
})

const regulationSummary = computed<SafetyRegulationTypeSummary | null>(() => {
  const summary = props.item.type_summary
  return summary?.kind === 'SAFETY_REGULATION' ? summary : null
})

const caseStatusMap = {
  CLOSED: { label: '已结案', tone: 'verified' },
  CORRECTED: { label: '已更正', tone: 'info' },
  ENFORCEMENT_DECISION: { label: '处罚问责', tone: 'verified' },
  FINAL_INVESTIGATION_REPORT: { label: '正式调查', tone: 'verified' },
  INITIAL_OFFICIAL_REPORT: { label: '官方初报', tone: 'pending' },
  RECTIFICATION_FOLLOW_UP: { label: '整改跟进', tone: 'pending' },
  UNDER_INVESTIGATION: { label: '调查中', tone: 'pending' },
  UNVERIFIED_LEAD: { label: '线索待核实', tone: 'conflict' },
  WITHDRAWN: { label: '已撤回', tone: 'withdrawn' },
} as const satisfies Record<
  NonNullable<SafetyCaseTypeSummary['incident_status']>,
  { label: string; tone: StatusBadgeTone }
>

const caseStatus = computed<{ label: string; tone: StatusBadgeTone } | null>(() => {
  const summary = safetyCaseSummary.value
  if (!summary?.incident_status) return null
  if (summary.incident_status === 'RECTIFICATION_FOLLOW_UP' && summary.rectification_has_open_issues) {
    return { label: '整改评估完成但仍有问题', tone: 'conflict' }
  }
  return caseStatusMap[summary.incident_status]
})

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

function formatLoss(amountMinor: number, currency: string): string {
  const major = Math.trunc(amountMinor / 100)
  const minor = amountMinor % 100
  const formattedMajor = new Intl.NumberFormat('zh-CN').format(major)
  const formattedMinor = minor === 0 ? '' : `.${String(minor).padStart(2, '0')}`
  return `${formattedMajor}${formattedMinor} ${currency === 'CNY' ? '人民币元' : currency}`
}
</script>

<template>
  <article class="intelligence-card" :data-review-status="item.review_status">
    <div class="intelligence-card__meta">
      <span
        class="intelligence-card__type"
        :class="{ 'is-safety-case': item.content_type === 'SAFETY_CASE' }"
      >
        {{ item.content_type === 'SAFETY_CASE' ? '安全案例' : '安全规定' }}
      </span>
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
      <span v-if="caseStatus" data-testid="case-status">
        <StatusBadge :tone="caseStatus.tone" :label="caseStatus.label" />
      </span>
      <span
        v-if="safetyCaseSummary?.conflicted_fields?.length"
        data-testid="case-conflict"
      >
        <StatusBadge tone="conflict" label="冲突待核实" />
      </span>
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

    <template v-if="!isWithdrawn && item.publication_revision_id && regulationSummary">
      <dl class="intelligence-card__facts">
        <div>
          <dt>文号</dt>
          <dd>{{ regulationSummary.document_number }}</dd>
        </div>
        <div>
          <dt>发布机关</dt>
          <dd>{{ regulationSummary.issuing_authority }}</dd>
        </div>
        <div>
          <dt>效力状态</dt>
          <dd>
            {{ regulationSummary.regulation_status === 'UNKNOWN' ? '效力状态待核验' : regulationSummary.regulation_status }}
          </dd>
        </div>
      </dl>
    </template>

    <template v-else-if="!isWithdrawn && item.publication_revision_id && safetyCaseSummary">
      <dl class="intelligence-card__facts is-safety-case">
        <div v-if="safetyCaseSummary.engineering_type">
          <dt>工程类型</dt>
          <dd>{{ safetyEngineeringLabel(safetyCaseSummary.engineering_type) }}</dd>
        </div>
        <div v-if="safetyCaseSummary.hazard_type">
          <dt>事故类型</dt>
          <dd>{{ safetyHazardLabel(safetyCaseSummary.hazard_type) }}</dd>
        </div>
        <div v-if="safetyCaseSummary.occurred_at">
          <dt>发生时间</dt>
          <dd>{{ formatDate(safetyCaseSummary.occurred_at) }}</dd>
        </div>
        <div v-if="safetyCaseSummary.region">
          <dt>地区</dt>
          <dd>{{ safetyCaseSummary.region }}</dd>
        </div>
        <div v-if="hasValue(safetyCaseSummary.deaths)">
          <dt>死亡人数</dt>
          <dd>{{ safetyCaseSummary.deaths }} 人</dd>
        </div>
        <div v-if="hasValue(safetyCaseSummary.injuries)">
          <dt>受伤人数</dt>
          <dd>{{ safetyCaseSummary.injuries }} 人</dd>
        </div>
        <div
          v-if="safetyCaseSummary.loss_amount_minor !== null
            && safetyCaseSummary.loss_amount_minor !== undefined
            && safetyCaseSummary.loss_currency"
        >
          <dt>直接经济损失</dt>
          <dd>
            {{ formatLoss(safetyCaseSummary.loss_amount_minor, safetyCaseSummary.loss_currency) }}
          </dd>
        </div>
        <div v-if="safetyCaseSummary.official_direct_causes?.length">
          <dt>正式原因</dt>
          <dd>{{ safetyCaseSummary.official_direct_causes.length }} 项已审核认定</dd>
        </div>
        <div v-if="safetyCaseSummary.responsibility_findings?.length">
          <dt>责任认定</dt>
          <dd>{{ safetyCaseSummary.responsibility_findings.length }} 项已审核认定</dd>
        </div>
      </dl>
    </template>

    <footer class="intelligence-card__footer">
      <a :href="item.original_url" target="_blank" rel="noreferrer">
        {{ originalLinkLabel }}
      </a>
      <a
        v-if="safetyCaseSummary?.event_id"
        :href="`/events/${safetyCaseSummary.event_id}`"
        data-testid="event-link"
      >
        查看事件时间线
      </a>
      <button
        v-if="item.publication_revision_id && item.evidence_status === 'VERIFIED'"
        type="button"
        data-testid="evidence-trigger"
        @click="emit('evidence', item.id)"
      >
        {{ isWithdrawn ? '查看历史证据' : '查看证据' }}（{{ item.evidence_count ?? 0 }}）
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

.intelligence-card__type {
  color: var(--color-safetyRegulation-700);
  background: var(--color-safetyRegulation-50);
}

.intelligence-card__type.is-safety-case {
  color: var(--color-safetyCase-700);
  background: var(--color-safetyCase-50);
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

.intelligence-card__facts.is-safety-case {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  background: var(--color-safetyCase-50);
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

  .intelligence-card__source,
  .intelligence-card__facts.is-safety-case {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 40.001rem) and (max-width: 63.999rem) {
  .intelligence-card__facts.is-safety-case {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
