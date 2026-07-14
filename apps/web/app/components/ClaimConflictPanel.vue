<script setup lang="ts">
import type { ClaimConflict, ClaimConflictDecisionRequest } from '@srbg/contracts'
import { EmptyState, Skeleton, StatusBadge } from '@srbg/ui'
import { reactive } from 'vue'

withDefaults(
  defineProps<{
    conflicts: readonly ClaimConflict[]
    loading: boolean
    busyConflictId: string | null
    errorMessage?: string | null
    successMessage?: string | null
  }>(),
  {
    errorMessage: null,
    successMessage: null,
  },
)

const emit = defineEmits<{
  decide: [conflictId: string, decision: ClaimConflictDecisionRequest]
}>()

const reasons = reactive<Record<string, string>>({})

const fieldLabels: Readonly<Record<ClaimConflict['field'], string>> = {
  DEATH_COUNT: '死亡人数',
  INJURY_COUNT: '受伤人数',
  LOSS_AMOUNT_MINOR: '直接经济损失（最小货币单位）',
  OFFICIAL_DIRECT_CAUSES: '正式调查认定的直接原因',
  RESPONSIBILITY_FINDINGS: '责任认定',
}

function fieldLabel(field: ClaimConflict['field']): string {
  return fieldLabels[field]
}

function displayValue(value: ClaimConflict['current_value']): string {
  if (value === null) return '暂无已确认事实'
  return Array.isArray(value) ? value.join('；') : String(value)
}

function hasReason(conflictId: string): boolean {
  return Boolean(reasons[conflictId]?.trim())
}

function decide(
  conflictId: string,
  action: ClaimConflictDecisionRequest['action'],
): void {
  const reason = reasons[conflictId]?.trim()
  if (!reason) return
  emit('decide', conflictId, { action, reason })
}
</script>

<template>
  <section class="claim-conflict-panel" aria-labelledby="claim-conflict-title">
    <header class="claim-conflict-panel__header">
      <div>
        <p>Reviewer 专属 · 服务端 ACL</p>
        <h2 id="claim-conflict-title">关键字段冲突</h2>
      </div>
      <StatusBadge tone="conflict" label="人工裁决必需" />
    </header>

    <aside class="claim-conflict-panel__separation" role="note">
      <StatusBadge tone="pending" label="职责分离" />
      <p>
        提交人不得审批自己提交的安全案例。所有决定由服务端校验审核人身份并写入审计记录。
      </p>
    </aside>

    <p v-if="successMessage" class="claim-conflict-panel__success" role="status">
      {{ successMessage }}
    </p>
    <p v-if="errorMessage" class="claim-conflict-panel__error" role="alert">
      {{ errorMessage }}
    </p>

    <Skeleton v-if="loading" :lines="5" label="正在加载关键字段冲突" />
    <ol v-else-if="conflicts.length" class="claim-conflict-panel__list">
      <li v-for="conflict in conflicts" :key="conflict.id">
        <article :aria-labelledby="`conflict-${conflict.id}-title`">
          <header>
            <div>
              <p>事件 <a :href="`/events/${conflict.event_id}`">{{ conflict.event_id }}</a></p>
              <h3 :id="`conflict-${conflict.id}-title`">{{ fieldLabel(conflict.field) }}</h3>
            </div>
            <StatusBadge
              :tone="conflict.status === 'RESOLVED' ? 'verified' : 'conflict'"
              :label="conflict.status === 'RESOLVED' ? '已处理' : '冲突待核实'"
            />
          </header>

          <dl class="claim-conflict-panel__comparison">
            <div>
              <dt>当前已确认事实</dt>
              <dd>{{ displayValue(conflict.current_value) }}</dd>
            </div>
            <div>
              <dt>候选事实</dt>
              <dd>{{ displayValue(conflict.candidate_value) }}</dd>
            </div>
          </dl>

          <p v-if="conflict.resolution_reason" class="claim-conflict-panel__resolution">
            处理理由：{{ conflict.resolution_reason }}
          </p>

          <fieldset
            v-if="conflict.status === 'PENDING_REVIEW'"
            class="claim-conflict-panel__decision"
            data-testid="conflict-actions"
          >
            <legend>{{ fieldLabel(conflict.field) }}冲突处理</legend>
            <label :for="`conflict-${conflict.id}-reason`">
              {{ fieldLabel(conflict.field) }}冲突的处理理由
            </label>
            <textarea
              :id="`conflict-${conflict.id}-reason`"
              v-model="reasons[conflict.id]"
              required
              minlength="1"
              maxlength="1000"
              rows="3"
              :disabled="busyConflictId === conflict.id"
            />
            <p>理由为必填项，最多 1000 字；候选值不会自动覆盖当前事实。</p>
            <div class="claim-conflict-panel__actions">
              <button
                type="button"
                data-testid="conflict-action"
                data-action="KEEP_CURRENT"
                :disabled="!hasReason(conflict.id) || busyConflictId === conflict.id"
                @click="decide(conflict.id, 'KEEP_CURRENT')"
              >
                保留当前事实
              </button>
              <button
                type="button"
                data-testid="conflict-action"
                data-action="ACCEPT_CANDIDATE"
                :disabled="!hasReason(conflict.id) || busyConflictId === conflict.id"
                @click="decide(conflict.id, 'ACCEPT_CANDIDATE')"
              >
                采用候选事实
              </button>
              <button
                type="button"
                data-testid="conflict-action"
                data-action="MARK_UNRESOLVED"
                :disabled="!hasReason(conflict.id) || busyConflictId === conflict.id"
                @click="decide(conflict.id, 'MARK_UNRESOLVED')"
              >
                继续待核实
              </button>
            </div>
          </fieldset>
        </article>
      </li>
    </ol>
    <EmptyState
      v-else
      title="暂无关键字段冲突"
      description="伤亡、损失、原因或责任出现差异时，会在这里等待审核员裁决。"
      icon="ShieldCheck"
    />
  </section>
</template>

<style scoped>
.claim-conflict-panel {
  display: grid;
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-conflict-500);
  border-radius: var(--radius-lg);
  gap: var(--spacing-4);
}

.claim-conflict-panel__header,
.claim-conflict-panel article > header,
.claim-conflict-panel__separation,
.claim-conflict-panel__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.claim-conflict-panel__header p,
.claim-conflict-panel article > header p {
  margin: 0 0 var(--spacing-1);
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.claim-conflict-panel h2,
.claim-conflict-panel h3 {
  margin: 0;
  color: var(--color-ink-900);
}

.claim-conflict-panel__separation,
.claim-conflict-panel__success,
.claim-conflict-panel__error {
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-sm);
}

.claim-conflict-panel__separation {
  justify-content: flex-start;
  color: var(--color-ink-700);
  background: var(--color-reviewPending-50);
}

.claim-conflict-panel__separation p,
.claim-conflict-panel__success,
.claim-conflict-panel__error {
  margin: 0;
}

.claim-conflict-panel__success {
  color: var(--color-verified-700);
  background: var(--color-verified-50);
}

.claim-conflict-panel__error {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

.claim-conflict-panel__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
  gap: var(--spacing-4);
}

.claim-conflict-panel article {
  display: grid;
  padding: var(--spacing-4);
  background: var(--color-canvas);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  gap: var(--spacing-4);
}

.claim-conflict-panel a {
  color: var(--color-brand-700);
}

.claim-conflict-panel__comparison {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
  gap: var(--spacing-3);
}

.claim-conflict-panel__comparison > div {
  padding: var(--spacing-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.claim-conflict-panel__comparison dt,
.claim-conflict-panel__decision > p {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.claim-conflict-panel__comparison dd {
  margin: var(--spacing-2) 0 0;
  color: var(--color-ink-900);
  font-family: var(--font-numeric);
  font-size: var(--text-lg);
  font-weight: var(--font-weight-semibold);
}

.claim-conflict-panel__resolution {
  margin: 0;
  color: var(--color-ink-700);
}

.claim-conflict-panel__decision {
  display: grid;
  margin: 0;
  padding: var(--spacing-4);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  gap: var(--spacing-2);
}

.claim-conflict-panel__decision legend,
.claim-conflict-panel__decision label {
  color: var(--color-ink-800);
  font-weight: var(--font-weight-semibold);
}

.claim-conflict-panel__decision textarea {
  width: 100%;
  padding: var(--spacing-3);
  color: var(--color-ink-900);
  font: inherit;
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  resize: vertical;
}

.claim-conflict-panel__decision > p {
  margin: 0;
}

.claim-conflict-panel__actions {
  justify-content: flex-start;
  margin-top: var(--spacing-2);
}

.claim-conflict-panel__actions button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-4);
  color: var(--color-brand-700);
  font: inherit;
  font-weight: var(--font-weight-semibold);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.claim-conflict-panel__actions button[data-action='ACCEPT_CANDIDATE'] {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}

.claim-conflict-panel__actions button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

@media (max-width: 47.999rem) {
  .claim-conflict-panel {
    padding: var(--spacing-4);
  }

  .claim-conflict-panel__comparison {
    grid-template-columns: 1fr;
  }

  .claim-conflict-panel__actions button {
    width: 100%;
  }
}
</style>
