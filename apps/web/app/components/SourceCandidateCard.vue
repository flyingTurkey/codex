<script setup lang="ts">
import { StatusBadge } from '@srbg/ui'
import { computed } from 'vue'

import type { SourceCandidateCardProjection } from '../source-center'
import {
  candidateCanBatchSelect,
  candidateCanDismiss,
  candidateCanEnable,
  candidateCanRequestQualification,
  formatShanghaiDateTime,
  qualificationVerdictLabel,
  qualificationVerdictTone,
} from '../source-center'

const props = withDefaults(defineProps<{
  busy?: boolean
  candidate: SourceCandidateCardProjection
  roles: readonly string[]
  selected?: boolean
}>(), {
  busy: false,
  selected: false,
})

const emit = defineEmits<{
  decision: [decision: 'DISMISS' | 'ENABLE']
  qualification: []
  select: [selected: boolean]
}>()

const canBatchSelect = computed(() => candidateCanBatchSelect(props.candidate, props.roles))
const canDismiss = computed(() => candidateCanDismiss(props.candidate, props.roles))
const canEnable = computed(() => candidateCanEnable(props.candidate, props.roles))
const canRequestQualification = computed(() => (
  candidateCanRequestQualification(props.candidate, props.roles)
))
const qualification = computed(() => props.candidate.latest_qualification)

function toggleSelection(event: Event): void {
  const input = event.currentTarget
  if (input instanceof HTMLInputElement) emit('select', input.checked)
}
</script>

<template>
  <article class="source-candidate-card" :aria-labelledby="`candidate-title-${candidate.id}`">
    <div class="source-candidate-card__header">
      <label v-if="canBatchSelect" class="source-candidate-card__selection">
        <input
          type="checkbox"
          :checked="selected"
          :disabled="busy"
          :aria-label="`选择 ${candidate.institution_name} 批量启用`"
          @change="toggleSelection"
        >
      </label>
      <div class="source-candidate-card__identity">
        <p>{{ candidate.authorization_boundary }}</p>
        <h2 :id="`candidate-title-${candidate.id}`">{{ candidate.institution_name }}</h2>
        <a :href="candidate.canonical_url" target="_blank" rel="noopener noreferrer">
          {{ candidate.canonical_url }}
        </a>
      </div>
      <div class="source-candidate-card__badges">
        <StatusBadge
          :tone="qualificationVerdictTone(candidate)"
          :label="qualificationVerdictLabel(candidate)"
        />
        <StatusBadge
          :tone="!qualification ? 'pending' : qualification.storage_policy === 'RAW_EVIDENCE_ALLOWED' ? 'verified' : 'info'"
          :label="!qualification ? '证据策略待定' : qualification.storage_policy === 'RAW_EVIDENCE_ALLOWED' ? '私有原始证据' : qualification.storage_policy === 'METADATA_ONLY' ? '受限题录' : '仅原文链接'"
        />
      </div>
    </div>

    <div class="source-candidate-card__dimensions" aria-label="来源覆盖维度">
      <span>{{ (candidate.industries ?? []).join(' / ') || '行业待识别' }}</span>
      <span>{{ (candidate.content_domains ?? []).join(' / ') || '内容域待识别' }}</span>
      <span>{{ (candidate.language_tags ?? []).join(' / ') || '语言待识别' }}</span>
      <span>{{ candidate.discovery_channels.join(' / ') || '发现渠道待记录' }}</span>
    </div>

    <dl v-if="qualification" class="source-candidate-card__metrics">
      <div><dt>样本</dt><dd>{{ qualification.sampled_item_count }}</dd></div>
      <div><dt>相关内容</dt><dd>{{ qualification.relevant_item_count }}</dd></div>
      <div><dt>重复发现</dt><dd>{{ candidate.occurrence_count }}</dd></div>
      <div><dt>规则版本</dt><dd>{{ qualification.rule_version }}</dd></div>
      <div><dt>资格有效期</dt><dd>{{ formatShanghaiDateTime(qualification.expires_at) }}</dd></div>
    </dl>
    <p v-else class="source-candidate-card__pending" role="status">
      尚无服务端资格包；不能启用。
    </p>

    <ul v-if="qualification?.reason_codes?.length" class="source-candidate-card__reasons" aria-label="资格原因">
      <li v-for="reasonCode in qualification.reason_codes ?? []" :key="reasonCode">{{ reasonCode }}</li>
    </ul>

    <div class="source-candidate-card__actions">
      <button
        v-if="canRequestQualification"
        class="secondary-button"
        type="button"
        :disabled="busy"
        @click="emit('qualification')"
      >
        重新资格审核
      </button>
      <button
        v-if="canDismiss"
        class="secondary-button"
        data-decision="DISMISS"
        type="button"
        :disabled="busy"
        @click="emit('decision', 'DISMISS')"
      >
        不启用
      </button>
      <button
        v-if="canEnable"
        class="primary-button"
        data-decision="ENABLE"
        type="button"
        :disabled="busy"
        @click="emit('decision', 'ENABLE')"
      >
        启用
      </button>
    </div>
  </article>
</template>

<style scoped>
.source-candidate-card {
  display: grid;
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  gap: var(--spacing-4);
}

.source-candidate-card__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--spacing-3);
}

.source-candidate-card__selection {
  display: grid;
  min-width: var(--spacing-10);
  min-height: var(--spacing-10);
  place-items: center;
}

.source-candidate-card__selection input {
  width: var(--spacing-4);
  height: var(--spacing-4);
}

.source-candidate-card__identity {
  min-width: 0;
}

.source-candidate-card__identity h2,
.source-candidate-card__identity p {
  margin: 0;
}

.source-candidate-card__identity h2 {
  color: var(--color-ink-900);
  font-size: var(--text-lg);
  line-height: var(--srbg-font-line-height-title);
}

.source-candidate-card__identity p,
.source-candidate-card__identity a {
  overflow: hidden;
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-candidate-card__identity a {
  display: block;
  margin-top: var(--spacing-1);
}

.source-candidate-card__badges,
.source-candidate-card__dimensions,
.source-candidate-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.source-candidate-card__badges,
.source-candidate-card__actions {
  justify-content: flex-end;
}

.source-candidate-card__dimensions {
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.source-candidate-card__dimensions span {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-pill);
}

.source-candidate-card__metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin: 0;
  padding-block: var(--spacing-3);
  border-block: 1px solid var(--color-border);
  gap: var(--spacing-3);
}

.source-candidate-card__metrics div {
  display: grid;
  min-width: 0;
  gap: var(--spacing-1);
}

.source-candidate-card__metrics dt {
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.source-candidate-card__metrics dd {
  margin: 0;
  overflow: hidden;
  color: var(--color-ink-900);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-candidate-card__reasons {
  display: flex;
  flex-wrap: wrap;
  margin: 0;
  padding: 0;
  color: var(--color-conflict-700);
  list-style: none;
  gap: var(--spacing-2);
}

.source-candidate-card__reasons li {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--color-conflict-50);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.source-candidate-card__pending {
  margin: 0;
  color: var(--color-reviewPending-700);
}

.primary-button,
.secondary-button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-4);
  border: 1px solid var(--color-brand-700);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.primary-button {
  color: var(--color-surface);
  background: var(--color-brand-700);
}

.secondary-button {
  color: var(--color-brand-700);
  background: var(--color-surface);
}

button:disabled {
  cursor: wait;
  opacity: 0.6;
}

@media (max-width: 63.999rem) {
  .source-candidate-card__header {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .source-candidate-card__badges {
    grid-column: 2;
    justify-content: flex-start;
  }

  .source-candidate-card__metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 39.999rem) {
  .source-candidate-card__metrics {
    grid-template-columns: 1fr;
  }

  .source-candidate-card__actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
