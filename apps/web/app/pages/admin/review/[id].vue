<script setup lang="ts">
import type {
  ClaimView,
  EvidenceView,
  DigitalCaseReviewPatch,
  ReviewCandidateDecisionRequest,
  ReviewDecisionRequest,
  ReviewDecisionResponse,
  ReviewTaskDetail,
} from '@srbg/contracts'
import { PageHeader, StatusBadge } from '@srbg/ui'
import { computed, ref, watch } from 'vue'

import EvidenceDrawer from '../../../components/EvidenceDrawer.vue'
import IntelligenceCard from '../../../components/IntelligenceCard.vue'
import ReviewWorkbench from '../../../components/ReviewWorkbench.vue'

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
const engineeringDomains = ref('')
const lifecycleStages = ref('')
const technologyTags = ref('')
const applicationScenarios = ref('')
const maturityLevel = ref<DigitalCaseReviewPatch['maturity_level']>('UNKNOWN')
const maturityEvidenceIds = ref<string[]>([])
const outcomeEntities = ref<Record<string, string>>({})
const outcomeVerification = ref<Record<string, 'CLAIMED' | 'VERIFIED'>>({})

const isSafetyCase = computed(() => detail.value?.item.content_type === 'SAFETY_CASE')
const isDigitalCase = computed(() => detail.value?.item.content_type === 'DIGITAL_CASE')
const isClaimReview = computed(() => detail.value?.task.task_type === 'CLAIM_REVIEW')
const digitalOutcomes = computed(() => [
  ...(detail.value?.digital_case?.claimed_outcomes ?? []),
  ...(detail.value?.digital_case?.verified_outcomes ?? []),
])
watch(
  () => detail.value?.digital_case,
  (digitalCase) => {
    if (!digitalCase) return
    engineeringDomains.value = digitalCase.engineering_domains.join(', ')
    lifecycleStages.value = digitalCase.lifecycle_stages.join(', ')
    technologyTags.value = digitalCase.technology_tags.join(', ')
    applicationScenarios.value = digitalCase.application_scenarios.join(', ')
    maturityLevel.value = digitalCase.maturity_level
    for (const outcome of [...digitalCase.claimed_outcomes, ...digitalCase.verified_outcomes]) {
      const entity = digitalCase.entities.find((candidate) => candidate.name === outcome.attribution)
      outcomeEntities.value[outcome.id] = entity?.id ?? ''
      outcomeVerification.value[outcome.id] = outcome.verification
    }
  },
  { immediate: true },
)
const pendingSafetyClaims = computed(() =>
  (isSafetyCase.value || isClaimReview.value)
    ? (detail.value?.claims ?? []).filter((claim) => claim.decision_status === 'PENDING')
    : [],
)
const digitalPatchIncomplete = computed(() => isDigitalCase.value && (
  !engineeringDomains.value.trim()
  || !lifecycleStages.value.trim()
  || !technologyTags.value.trim()
  || !applicationScenarios.value.trim()
  || digitalOutcomes.value.some((outcome) => !outcomeEntities.value[outcome.id])
))
const publishBlocked = computed(() => pendingSafetyClaims.value.length > 0 || digitalPatchIncomplete.value)
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
    const codes = (value: string): string[] => value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    const digital_case_patch = action === 'APPROVE' && isDigitalCase.value
      ? {
          engineering_domains: codes(engineeringDomains.value),
          lifecycle_stages: codes(lifecycleStages.value),
          technology_tags: codes(technologyTags.value),
          application_scenarios: codes(applicationScenarios.value),
          maturity_level: maturityLevel.value,
          maturity_evidence_ids: maturityEvidenceIds.value,
          outcome_attributions: digitalOutcomes.value.map((outcome) => ({
            outcome_id: outcome.id,
            attribution_entity_id: outcomeEntities.value[outcome.id] ?? '',
            verification: outcomeVerification.value[outcome.id] ?? 'CLAIMED',
            independent_evidence_ids:
              outcomeVerification.value[outcome.id] === 'VERIFIED'
                ? outcome.independent_evidence_ids
                : [],
          })),
        } satisfies DigitalCaseReviewPatch
      : undefined
    const body = {
      action,
      reason: reason.value,
      ...(digital_case_patch ? { digital_case_patch } : {}),
    } satisfies ReviewDecisionRequest
    await $fetch<ReviewDecisionResponse>(
      `/api/v1/admin/review-tasks/${taskId}/decisions`,
      { method: 'POST', body },
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
      <ReviewWorkbench :detail="detail" @evidence="openAllEvidence" />
      <section class="review-detail__item" aria-labelledby="review-item-title">
        <h2 id="review-item-title">待审核内容</h2>
        <IntelligenceCard :item="detail.item" />
      </section>

      <section class="review-detail__claims">
        <h2>{{ isSafetyCase || isClaimReview ? '候选事实逐项审核' : '规则解析字段' }}</h2>
        <p v-if="isSafetyCase || isClaimReview" class="review-detail__field-rule">
          原因、责任、伤亡和损失必须逐字段核对正式证据。提交人不得审批自己提交的安全案例。
        </p>
        <div v-if="isSafetyCase || isClaimReview" class="review-detail__claim-list">
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

      <section v-if="isDigitalCase && !isClaimReview && detail.digital_case" class="review-detail__digital-patch">
        <h2>数字化案例结构审核</h2>
        <p>只能选择已有接受证据支持的代码；服务端会重新计算相关性 v1。</p>
        <div class="review-detail__digital-grid">
          <label>工程专业代码<input v-model="engineeringDomains" placeholder="BRIDGE, HIGHWAY"></label>
          <label>生命周期代码<input v-model="lifecycleStages" placeholder="CONSTRUCTION"></label>
          <label>技术标签代码<input v-model="technologyTags" placeholder="BIM, IOT"></label>
          <label>应用场景代码<input v-model="applicationScenarios" placeholder="QUALITY_CONTROL"></label>
          <label>
            成熟度
            <select v-model="maturityLevel">
              <option value="CONCEPT">概念</option>
              <option value="LAB_PROTOTYPE">实验室原型</option>
              <option value="ENGINEERING_PROTOTYPE">工程样机</option>
              <option value="PILOT">试点</option>
              <option value="SINGLE_PROJECT_PRODUCTION">单项目生产应用</option>
              <option value="MULTI_PROJECT_REPLICATION">多项目复制</option>
              <option value="ENTERPRISE_SCALE">企业规模应用</option>
              <option value="UNKNOWN">未知</option>
            </select>
          </label>
        </div>
        <fieldset class="review-detail__maturity-evidence">
          <legend>成熟度证据</legend>
          <label v-for="evidenceItem in detail.evidence" :key="evidenceItem.id">
            <input v-model="maturityEvidenceIds" type="checkbox" :value="evidenceItem.id">
            {{ evidenceItem.excerpt }}
          </label>
        </fieldset>
        <div class="review-detail__attributions">
          <h3>成效归因</h3>
          <article v-for="outcome in digitalOutcomes" :key="outcome.id">
            <p>{{ outcome.statement }}</p>
            <label>
              归因主体
              <select v-model="outcomeEntities[outcome.id]">
                <option value="" disabled>请选择证据中的主体</option>
                <option v-for="entity in detail.digital_case.entities" :key="entity.id" :value="entity.id">
                  {{ entity.name }}
                </option>
              </select>
            </label>
            <label>
              证据性质
              <select v-model="outcomeVerification[outcome.id]">
                <option value="CLAIMED">发布方声明</option>
            <option value="VERIFIED" :disabled="!outcome.independent_evidence_ids?.length">独立验证</option>
              </select>
            </label>
          </article>
        </div>
      </section>

      <form v-if="!isClaimReview && detail.task.status === 'PENDING'" class="review-detail__decision" @submit.prevent>
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
.review-detail__decision,
.review-detail__digital-patch {
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.review-detail__digital-patch {
  display: grid;
  gap: var(--spacing-4);
}

.review-detail__digital-patch h2,
.review-detail__digital-patch h3,
.review-detail__digital-patch p {
  margin: 0;
}

.review-detail__digital-grid,
.review-detail__attributions article {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-3);
}

.review-detail__digital-grid label,
.review-detail__attributions label,
.review-detail__maturity-evidence label {
  display: grid;
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  gap: var(--spacing-2);
}

.review-detail__digital-grid input,
.review-detail__digital-grid select,
.review-detail__attributions select {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.review-detail__maturity-evidence {
  display: grid;
  margin: 0;
  padding: var(--spacing-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  gap: var(--spacing-2);
}

.review-detail__maturity-evidence label {
  grid-template-columns: auto 1fr;
}

.review-detail__attributions {
  display: grid;
  gap: var(--spacing-3);
}

.review-detail__attributions article {
  padding: var(--spacing-3);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
}

.review-detail__attributions article p {
  grid-column: 1 / -1;
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

  .review-detail__digital-grid,
  .review-detail__attributions article {
    grid-template-columns: 1fr;
  }
}
</style>
