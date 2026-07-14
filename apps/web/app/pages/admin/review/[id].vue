<script setup lang="ts">
import type {
  ClaimView,
  EvidenceView,
  ReviewCandidateDecisionRequest,
  ReviewDecisionResponse,
  ReviewTaskDetail,
} from '@srbg/contracts'
import { PageHeader, StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

import EvidenceDrawer from '../../../components/EvidenceDrawer.vue'
import IntelligenceCard from '../../../components/IntelligenceCard.vue'

const route = useRoute()
const taskId = String(route.params.id)
const { data: detail, status, error, refresh } = await useFetch<ReviewTaskDetail>(
  `/api/v1/admin/review-tasks/${taskId}`,
  { server: false, retry: 0, timeout: 5_000 },
)
const reason = ref('字段与官方原文证据一致')
const submitting = ref(false)
const decisionError = ref<string | null>(null)
const evidenceOpen = ref(false)
const evidenceClaimId = ref<string | null>(null)
const claimReasons = ref<Record<string, string>>({})
const claimSubmittingId = ref<string | null>(null)
const claimDecisionErrors = ref<Record<string, string>>({})

const isSafetyCase = computed(() => detail.value?.item.content_type === 'SAFETY_CASE')
const pendingSafetyClaims = computed(() =>
  isSafetyCase.value
    ? (detail.value?.claims ?? []).filter((claim) => claim.decision_status === 'PENDING')
    : [],
)
const publishBlocked = computed(() => pendingSafetyClaims.value.length > 0)
const drawerClaims = computed<ClaimView[]>(() => {
  if (!detail.value) return []
  if (!evidenceClaimId.value) return detail.value.claims
  return detail.value.claims.filter((claim) => claim.id === evidenceClaimId.value)
})
const drawerEvidence = computed<EvidenceView[]>(() => {
  if (!detail.value || !evidenceClaimId.value) return detail.value?.evidence ?? []
  const evidenceIds = new Set(drawerClaims.value.flatMap((claim) => claim.evidence_ids))
  return detail.value.evidence.filter((evidence) => evidenceIds.has(evidence.id))
})

function evidenceForClaim(claim: ClaimView): EvidenceView[] {
  const evidenceIds = new Set(claim.evidence_ids)
  return (detail.value?.evidence ?? []).filter((evidence) => evidenceIds.has(evidence.id))
}

function openAllEvidence(): void {
  evidenceClaimId.value = null
  evidenceOpen.value = true
}

function openClaimEvidence(claimId: string): void {
  evidenceClaimId.value = claimId
  evidenceOpen.value = true
}

async function decideClaim(claim: ClaimView, action: 'ACCEPT' | 'REJECT'): Promise<void> {
  const claimReason = claimReasons.value[claim.id]?.trim() ?? ''
  if (claim.decision_status !== 'PENDING' || !claimReason) return

  claimSubmittingId.value = claim.id
  claimDecisionErrors.value[claim.id] = ''
  try {
    const body = {
      action,
      reason: claimReason,
      target_document_id: null,
    } satisfies ReviewCandidateDecisionRequest
    await $fetch(`/api/v1/admin/review-candidates/CLAIM/${claim.id}/decisions`, {
      method: 'POST',
      body,
      retry: 0,
      timeout: 5_000,
    })
    await refresh()
    claimReasons.value[claim.id] = ''
  } catch {
    claimDecisionErrors.value[claim.id] = '字段审核决定未能保存；字段状态未改变，请重试。'
  } finally {
    claimSubmittingId.value = null
  }
}

async function decide(action: 'APPROVE' | 'REJECT'): Promise<void> {
  if (action === 'APPROVE' && publishBlocked.value) {
    decisionError.value = '所有关键字段完成接受或拒绝后，才能批准并发布。'
    return
  }
  submitting.value = true
  decisionError.value = null
  try {
    await $fetch<ReviewDecisionResponse>(
      `/api/v1/admin/review-tasks/${taskId}/decisions`,
      { method: 'POST', body: { action, reason: reason.value } },
    )
    await refresh()
  } catch {
    decisionError.value = '审核决定未能提交，请检查职责分离与发布门禁。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="review-detail">
    <PageHeader
      title="R3 审核详情"
      eyebrow="字段证据与发布门禁"
      description="候选内容自报的来源等级、评分或审核状态不作为授权依据。"
    />
    <p v-if="status === 'pending'" role="status">正在加载审核证据…</p>
    <p v-else-if="error" role="alert">审核详情暂时不可用。</p>
    <template v-else-if="detail">
      <StatusBadge
        :label="detail.task.status === 'PENDING' ? '待审核' : detail.task.status === 'APPROVED' ? '已批准' : '已拒绝'"
        :tone="detail.task.status === 'PENDING' ? 'pending' : detail.task.status === 'APPROVED' ? 'verified' : 'conflict'"
      />
      <section class="review-detail__item" aria-labelledby="review-item-title">
        <h2 id="review-item-title">待审核内容</h2>
        <IntelligenceCard :item="detail.item" />
      </section>

      <section class="review-detail__claims">
        <h2>{{ isSafetyCase ? '关键字段逐项审核' : '规则解析字段' }}</h2>
        <p v-if="isSafetyCase" class="review-detail__field-rule">
          原因、责任、伤亡和损失必须逐字段核对正式证据。提交人不得审批自己提交的安全案例。
        </p>
        <div v-if="isSafetyCase" class="review-detail__claim-list">
          <article
            v-for="claim in detail.claims"
            :key="claim.id"
            class="review-detail__claim"
          >
            <header>
              <div>
                <h3>{{ claim.label }}</h3>
                <p>{{ claim.value }}</p>
              </div>
              <StatusBadge
                v-if="claim.decision_status"
                :label="claim.decision_status === 'PENDING' ? '待逐字段审核' : claim.decision_status === 'ACCEPTED' ? '已接受' : '已拒绝'"
                :tone="claim.decision_status === 'PENDING' ? 'pending' : claim.decision_status === 'ACCEPTED' ? 'verified' : 'conflict'"
              />
            </header>

            <section
              v-if="evidenceForClaim(claim).length"
              class="review-detail__claim-evidence"
              :aria-label="`${claim.label}关联证据`"
            >
              <h4>关联正式证据</h4>
              <blockquote v-for="evidenceItem in evidenceForClaim(claim)" :key="evidenceItem.id">
                {{ evidenceItem.excerpt }}
              </blockquote>
              <button type="button" @click="openClaimEvidence(claim.id)">
                查看 {{ evidenceForClaim(claim).length }} 条定位证据
              </button>
            </section>

            <fieldset
              v-if="claim.decision_status === 'PENDING'"
              class="review-detail__claim-decision"
              :disabled="claimSubmittingId === claim.id"
            >
              <legend>{{ claim.label }}逐字段决定</legend>
              <label>
                {{ claim.label }}审核说明
                <textarea
                  v-model="claimReasons[claim.id]"
                  required
                  minlength="1"
                  maxlength="1000"
                />
              </label>
              <p v-if="claimDecisionErrors[claim.id]" role="alert">
                {{ claimDecisionErrors[claim.id] }}
              </p>
              <div>
                <button
                  type="button"
                  :disabled="!claimReasons[claim.id]?.trim()"
                  @click="decideClaim(claim, 'REJECT')"
                >
                  拒绝{{ claim.label }}
                </button>
                <button
                  type="button"
                  :disabled="!claimReasons[claim.id]?.trim()"
                  @click="decideClaim(claim, 'ACCEPT')"
                >
                  接受{{ claim.label }}
                </button>
              </div>
            </fieldset>
          </article>
        </div>
        <dl v-else>
          <div v-for="claim in detail.claims" :key="claim.id">
            <dt>{{ claim.label }}</dt>
            <dd>{{ claim.value }}</dd>
          </div>
        </dl>
        <button type="button" @click="openAllEvidence">
          打开 {{ detail.evidence.length }} 条段落证据
        </button>
      </section>

      <form v-if="detail.task.status === 'PENDING'" class="review-detail__decision" @submit.prevent>
        <label>
          审核说明
          <textarea v-model="reason" required minlength="1" maxlength="1000" />
        </label>
        <p
          v-if="publishBlocked"
          id="safety-case-publish-blocked"
          class="review-detail__publish-blocked"
          role="status"
        >
          所有关键字段完成接受或拒绝后，才能批准并发布。
        </p>
        <p v-if="decisionError" role="alert">{{ decisionError }}</p>
        <div>
          <button type="button" :disabled="submitting" @click="decide('REJECT')">拒绝</button>
          <button
            type="button"
            :disabled="submitting || publishBlocked"
            :aria-describedby="publishBlocked ? 'safety-case-publish-blocked' : undefined"
            @click="decide('APPROVE')"
          >
            批准并发布
          </button>
        </div>
      </form>
    </template>

    <EvidenceDrawer
      :open="evidenceOpen"
      :item-id="detail?.item.id"
      :claims="drawerClaims"
      :evidence="drawerEvidence"
      @close="evidenceOpen = false"
    />
  </section>
</template>

<style scoped>
.review-detail {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.review-detail__claims,
.review-detail__decision {
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.review-detail__item {
  display: grid;
  gap: var(--spacing-3);
}

.review-detail__item > h2,
.review-detail__claims h2 {
  margin: 0;
  color: var(--color-ink-900);
  font-size: var(--text-xl);
}

.review-detail__field-rule,
.review-detail__publish-blocked {
  margin: 0;
  padding: var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-reviewPending-50);
  border: 1px solid var(--color-reviewPending-200);
  border-radius: var(--radius-sm);
}

.review-detail__claim-list {
  display: grid;
  margin-top: var(--spacing-4);
  gap: var(--spacing-4);
}

.review-detail__claim {
  display: grid;
  padding: var(--spacing-4);
  background: var(--color-surfaceMuted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  gap: var(--spacing-4);
}

.review-detail__claim > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.review-detail__claim h3,
.review-detail__claim h4,
.review-detail__claim p,
.review-detail__claim blockquote {
  margin: 0;
}

.review-detail__claim h3 {
  color: var(--color-ink-900);
  font-size: var(--text-lg);
}

.review-detail__claim header p {
  margin-top: var(--spacing-1);
  color: var(--color-ink-700);
}

.review-detail__claim-evidence {
  display: grid;
  gap: var(--spacing-2);
}

.review-detail__claim-evidence h4 {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
}

.review-detail__claim-evidence blockquote {
  padding: var(--spacing-3);
  color: var(--color-ink-800);
  background: var(--color-surface);
  border-left: var(--spacing-1) solid var(--color-brand-400);
  border-radius: var(--radius-sm);
}

.review-detail__claim-evidence button {
  justify-self: start;
}

.review-detail__claim-decision {
  display: grid;
  margin: 0;
  padding: var(--spacing-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  gap: var(--spacing-3);
}

.review-detail__claim-decision legend {
  padding-inline: var(--spacing-1);
  color: var(--color-ink-700);
  font-weight: var(--font-weight-semibold);
}

.review-detail__claim-decision label {
  display: grid;
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  gap: var(--spacing-2);
}

.review-detail__claim-decision textarea {
  min-height: 5rem;
  padding: var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.review-detail__claim-decision > div {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

.review-detail__claims dl {
  display: grid;
  gap: var(--spacing-3);
}

.review-detail__claims dt,
.review-detail__decision label {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
}

.review-detail__claims dd {
  margin: var(--spacing-1) 0 0;
  color: var(--color-ink-900);
}

.review-detail__decision label {
  display: grid;
  gap: var(--spacing-2);
}

.review-detail__decision textarea {
  min-height: 6rem;
  padding: var(--spacing-3);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.review-detail__decision div {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  margin-top: var(--spacing-3);
}

.review-detail button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-brand-700);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.review-detail button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.review-detail button:last-child {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}

@media (max-width: 39.999rem) {
  .review-detail__claim > header,
  .review-detail__claim-decision > div,
  .review-detail__decision div {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
